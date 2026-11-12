"""Procesa updates de Telegram reutilizando AgentService + RuleEngine.

Flujo de clientes:
- Vinculación por código de pedido + DNI.
- Consultas respondidas por el agente.

Flujo de operadores:
- Vinculación con sus credenciales de Polux (`/vincular`).
- Aviso de casos con botones inline (ver / responder / cerrar).
- Respuesta al cliente citando el aviso o usando `/responder`.
- Modo conversación: tras "Responder", los mensajes van al caso hasta
  `/salir` (TTL de 2 horas).
"""
from __future__ import annotations

import hmac
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.core.security import verify_password
from app.models import (
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    CasoTelegramNotificacion,
    ClaseComunicacion,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    EstadoCaso,
    Pedido,
    Rol,
    RolCodigo,
    Usuario,
    UsuarioCasoActivo,
    UsuarioRol,
)
from app.schemas.agent import IncomingMessage
from app.services.agent_service import AgentService
from app.services.knowledge_base import es_consulta_conocida
from app.services.caso_service import (
    CasoError,
    cerrar_caso,
    reasignar_caso,
    responder_caso,
)
from app.services.telegram_service import TelegramService
from app.services.timeline_service import build_timeline

logger = get_logger("telegram_handler")

_WELCOME = (
    "👋 Bienvenido a Polux Import.\n\n"
    "Para consultar el estado de tu pedido, envíame tu código junto con tu DNI "
    "(por ejemplo: PD-2025-0001 70000001).\n\n"
    "Si necesitas hablar con un asesor, escribe tu consulta y te derivaré.\n\n"
    "Si eres operador, vincula tu cuenta con /vincular <email> <contraseña>."
)

_LINK_DNI_REQUIRED = (
    "Para vincular tu pedido necesito validar tu identidad.\n"
    "Envíame el código del pedido junto con tu DNI en un solo mensaje.\n"
    "Ejemplo: PD-2025-0001 70000001"
)

_LINK_INVALID = (
    "No pudimos validar el código y el DNI. Revisa los datos e inténtalo de nuevo.\n"
    "Si el problema continúa, escribe tu consulta y te derivaré con un asesor."
)

_LINK_ALREADY_LINKED = (
    "Ese pedido ya está vinculado a otra cuenta de Telegram.\n"
    "Por seguridad no puedo cambiarlo. Escribe tu consulta y te derivaré con un asesor."
)

_OPERATOR_LINK_HELP = (
    "Para vincular tu cuenta de operador envía:\n"
    "/vincular <email> <contraseña>\n"
    "Ejemplo: /vincular operador@poluximport.pe MiClaveSegura\n\n"
    "Puedes quitar la vinculación de este chat con /desvincular."
)

_OPERATOR_LINK_INVALID = (
    "No pudimos validar las credenciales, el usuario está inactivo o no tiene "
    "permisos de operador."
)

_OPERATOR_ALREADY_LINKED = (
    "Tu usuario ya está vinculado a otro chat de Telegram. Usa /desvincular "
    "desde ese chat o pide a un administrador que lo restablezca."
)

_OPERATOR_CHAT_TAKEN = (
    "Este chat ya está vinculado a otro usuario. Usa /desvincular primero."
)

_OPERATOR_TOO_MANY = (
    "Demasiados intentos fallidos. Espera unos minutos antes de volver a intentarlo."
)

_OPERATOR_HELP = (
    "Comandos de operador:\n"
    "/casos → casos abiertos o en proceso\n"
    "/caso <id> → ficha y línea de tiempo\n"
    "/responder <id> <mensaje> → responder al cliente\n"
    "/cerrar <id> → cerrar el caso\n"
    "/liberar <id> → soltar tu caso para que otro lo tome\n"
    "/salir → salir del modo respuesta\n\n"
    "También puedes pulsar los botones del aviso de un caso o responder "
    "citando ese mensaje."
)

_OPERATOR_COMMAND_HELP = {
    "/caso": "Uso: /caso <id>\nEjemplo: /caso 12",
    "/responder": (
        "Uso: /responder <id> <mensaje>\n"
        "Ejemplo: /responder 12 Hola, ya estamos revisando tu caso."
    ),
    "/cerrar": "Uso: /cerrar <id>\nEjemplo: /cerrar 12",
    "/liberar": (
        "Uso: /liberar <id>\n"
        "Ejemplo: /liberar 12\n"
        "El caso queda sin asignar para que otro operador lo tome."
    ),
}

# Roles que pueden recibir notificaciones y atender casos.
_OPERATOR_ROLES = {RolCodigo.ADMIN, RolCodigo.OPERADOR, RolCodigo.GERENTE}

# Límite básico de intentos por chat (en memoria, por proceso).
_MAX_FAILED_ATTEMPTS = 5
_FAILED_WINDOW_SECONDS = 15 * 60
_failed_attempts: dict[int, list[float]] = {}
_failed_lock = threading.Lock()

# Minutos que un operador permanece "dentro" de un caso tras responder.
_ACTIVE_CASE_TTL_MINUTES = 120
_MAX_TIMELINE_EVENTS = 12

_EVENT_ICONS = {
    "pedido": "📦",
    "hito": "🏁",
    "mensaje": "💬",
    "caso": "🚨",
    "imprevisto": "⚠️",
    "entrega": "🚚",
    "alerta": "🔔",
}


# ---------- Extractores ----------
def _msg(update: dict[str, Any]) -> dict[str, Any]:
    return update.get("message") or update.get("edited_message") or {}


def _chat_id(update: dict[str, Any]) -> int | None:
    cid = (_msg(update).get("chat") or {}).get("id")
    return int(cid) if cid is not None else None


def _text(update: dict[str, Any]) -> str | None:
    return _msg(update).get("text")


def _update_id(update: dict[str, Any]) -> int | None:
    uid = update.get("update_id")
    return int(uid) if uid is not None else None


def _external_id(update_id: int | None) -> str | None:
    return f"tg:{update_id}" if update_id is not None else None


def _reply_to_message_id(update: dict[str, Any]) -> int | None:
    rid = (_msg(update).get("reply_to_message") or {}).get("message_id")
    return int(rid) if rid is not None else None


def _callback(update: dict[str, Any]) -> dict[str, Any]:
    return update.get("callback_query") or {}


def _callback_chat_id(update: dict[str, Any]) -> int | None:
    cid = ((_callback(update).get("message") or {}).get("chat") or {}).get("id")
    return int(cid) if cid is not None else None


# ---------- Resolución ----------
def _resolve_cliente(db: Session, chat_id: int) -> Cliente | None:
    return db.scalar(select(Cliente).where(Cliente.telegram_chat_id == str(chat_id)))


def _resolve_pedido_activo(db: Session, cliente: Cliente) -> Pedido | None:
    return db.scalar(
        select(Pedido)
        .where(
            Pedido.cliente_id == cliente.id,
            Pedido.estado_actual.not_in(
                ["CERRADO", "CERRADO_CON_OBSERVACIONES", "CANCELADO"]
            ),
        )
        .order_by(Pedido.fecha_ingreso.desc())
        .limit(1)
    )


def _find_pedido_by_codigo(db: Session, codigo: str) -> Pedido | None:
    return db.scalar(select(Pedido).where(Pedido.codigo == codigo.strip().upper()))


def _resolve_operador(db: Session, chat_id: int | None) -> Usuario | None:
    if chat_id is None:
        return None
    usuario = db.scalar(
        select(Usuario).where(Usuario.telegram_chat_id == str(chat_id))
    )
    if usuario is None or not usuario.activo:
        return None
    if not (_usuario_roles(db, usuario.id) & _OPERATOR_ROLES):
        return None
    return usuario


# ---------- Verificación de identidad (código + DNI) ----------
def _norm_documento(value: str | None) -> str:
    """Normaliza el documento: sin espacios/guiones y en mayúsculas."""
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def _documento_matches(cliente: Cliente, documento: str | None) -> bool:
    esperado = _norm_documento(cliente.documento)
    recibido = _norm_documento(documento)
    if not esperado or not recibido:
        return False
    return hmac.compare_digest(esperado, recibido)


def _parse_pedido_link(text: str) -> tuple[str | None, str | None]:
    """Extrae (código, documento) de mensajes tipo:

    - ``PD-2025-0001 70000001``
    - ``PD-2025-0001 DNI 70000001``
    """
    parts = [p for p in re.split(r"[\s,;]+", text.strip()) if p]
    if not parts or not parts[0].upper().startswith("PD-"):
        return None, None

    codigo = parts[0].upper()
    resto = parts[1:]
    if resto and resto[0].upper() in {"DNI", "DOC", "DOCUMENTO", "CEDULA", "CÉDULA"}:
        resto = resto[1:]

    documento = "".join(resto) if resto else None
    if documento and not re.fullmatch(r"[A-Za-z0-9]{4,20}", documento):
        documento = None
    return codigo, documento


# ---------- Operadores (vinculación por credenciales) ----------
def _command_args(text: str, command: str) -> str | None:
    """Devuelve los argumentos de un comando, o None si no coincide.

    Soporta el sufijo @NombreDelBot que Telegram agrega en grupos.
    """
    partes = text.strip().split(maxsplit=1)
    if not partes:
        return None
    if partes[0].split("@", 1)[0].lower() != command:
        return None
    return partes[1].strip() if len(partes) > 1 else ""


def _too_many_failures(chat_id: int) -> bool:
    now = time.monotonic()
    with _failed_lock:
        recientes = [
            t for t in _failed_attempts.get(chat_id, [])
            if now - t < _FAILED_WINDOW_SECONDS
        ]
        if recientes:
            _failed_attempts[chat_id] = recientes
        else:
            _failed_attempts.pop(chat_id, None)
        return len(recientes) >= _MAX_FAILED_ATTEMPTS


def _register_failure(chat_id: int) -> None:
    with _failed_lock:
        _failed_attempts.setdefault(chat_id, []).append(time.monotonic())


def _clear_failures(chat_id: int) -> None:
    with _failed_lock:
        _failed_attempts.pop(chat_id, None)


def _find_usuario_by_email(db: Session, email: str) -> Usuario | None:
    return db.scalar(
        select(Usuario).where(func.lower(Usuario.email) == email.strip().lower())
    )


def _usuario_roles(db: Session, usuario_id: int) -> set[RolCodigo]:
    return set(
        db.scalars(
            select(Rol.codigo)
            .join(UsuarioRol, UsuarioRol.rol_id == Rol.id)
            .where(UsuarioRol.usuario_id == usuario_id)
        ).all()
    )


def _link_operator(
    db: Session,
    tg: TelegramService,
    chat_id: int,
    args: str,
    external_id: str | None,
) -> dict[str, Any]:
    partes = args.split(maxsplit=1)
    if len(partes) < 2:
        _log_comando(db, chat_id, "/vincular [credenciales]", None, None, external_id)
        _reply(db, tg, chat_id, _OPERATOR_LINK_HELP)
        return {"handled": "operator_help", "chat_id": chat_id}

    email, password = partes[0], partes[1]
    # Nunca persistimos ni logueamos la contraseña.
    _log_comando(
        db, chat_id, f"/vincular {email} [contraseña]", None, None, external_id,
    )

    if _too_many_failures(chat_id):
        _reply(db, tg, chat_id, _OPERATOR_TOO_MANY)
        return {"handled": "operator_rate_limited", "chat_id": chat_id}

    usuario = _find_usuario_by_email(db, email)
    roles = _usuario_roles(db, usuario.id) if usuario else set()
    valido = bool(
        usuario
        and usuario.activo
        and roles & _OPERATOR_ROLES
        and verify_password(password, usuario.password_hash)
    )
    if not valido:
        _register_failure(chat_id)
        _reply(db, tg, chat_id, _OPERATOR_LINK_INVALID)
        return {"handled": "operator_link_rejected", "chat_id": chat_id}

    ocupado = db.scalar(
        select(Usuario.id).where(
            Usuario.telegram_chat_id == str(chat_id),
            Usuario.id != usuario.id,
        )
    )
    if ocupado:
        _reply(db, tg, chat_id, _OPERATOR_CHAT_TAKEN)
        return {"handled": "operator_chat_taken", "chat_id": chat_id}

    if usuario.telegram_chat_id and usuario.telegram_chat_id != str(chat_id):
        _reply(db, tg, chat_id, _OPERATOR_ALREADY_LINKED)
        return {"handled": "operator_already_linked", "chat_id": chat_id}

    usuario.telegram_chat_id = str(chat_id)
    db.commit()
    _clear_failures(chat_id)
    _reply(
        db, tg, chat_id,
        f"✅ Vinculado como operador: {usuario.nombre_completo}. "
        "Recibirás las notificaciones de casos y podrás responderlos desde aquí.\n\n"
        f"{_OPERATOR_HELP}",
    )
    return {"handled": "operator_linked", "chat_id": chat_id, "usuario_id": usuario.id}


def _unlink_operator(
    db: Session, tg: TelegramService, chat_id: int, external_id: str | None,
) -> dict[str, Any]:
    _log_comando(db, chat_id, "/desvincular", None, None, external_id)
    usuario = db.scalar(
        select(Usuario).where(Usuario.telegram_chat_id == str(chat_id))
    )
    if usuario is None:
        _reply(db, tg, chat_id, "Este chat no está vinculado a ningún operador.")
        return {"handled": "operator_unlink_noop", "chat_id": chat_id}

    _clear_active_case(db, usuario)
    usuario.telegram_chat_id = None
    db.commit()
    _reply(db, tg, chat_id, "✅ Tu chat fue desvinculado. Ya no recibirás notificaciones.")
    return {"handled": "operator_unlinked", "chat_id": chat_id, "usuario_id": usuario.id}


# ---------- Persistencia de comandos (trazabilidad) ----------
def _log_comando(
    db: Session,
    chat_id: int,
    contenido: str,
    cliente: Cliente | None,
    pedido: Pedido | None,
    external_id: str | None,
    *,
    usuario_id: int | None = None,
) -> Comunicacion:
    com = Comunicacion(
        pedido_id=pedido.id if pedido else None,
        direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.TELEGRAM,
        contenido=contenido,
        autor=AutorComunicacion.CLIENTE,
        clase=ClaseComunicacion.OPERATIVO,
        usuario_id=usuario_id,
        escalado=False,
        whatsapp_message_id=external_id,
        fecha=datetime.utcnow(),
    )
    db.add(com)
    db.commit()
    db.refresh(com)
    return com


def _log_saliente_comando(
    db: Session,
    chat_id: int,
    contenido: str,
    cliente: Cliente | None,
    pedido: Pedido | None,
    estado: str,
    error: str | None = None,
    *,
    usuario_id: int | None = None,
) -> Comunicacion:
    com = Comunicacion(
        pedido_id=pedido.id if pedido else None,
        direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.TELEGRAM,
        contenido=contenido,
        autor=AutorComunicacion.AGENTE,
        clase=ClaseComunicacion.OPERATIVO,
        usuario_id=usuario_id,
        escalado=False,
        estado_entrega=estado,
        error_envio=(error or None) and error[:500],
        enviado_en=datetime.utcnow() if estado == "SENT" else None,
        fecha=datetime.utcnow(),
    )
    db.add(com)
    db.commit()
    db.refresh(com)
    return com


def _reply(
    db: Session,
    tg: TelegramService,
    chat_id: int,
    contenido: str,
    cliente: Cliente | None = None,
    pedido: Pedido | None = None,
    *,
    reply_markup: dict[str, Any] | None = None,
    usuario_id: int | None = None,
):
    """Envía una respuesta y la registra en `comunicacion`."""
    envio = tg.send_message(chat_id, contenido, reply_markup=reply_markup)
    _log_saliente_comando(
        db, chat_id, contenido, cliente, pedido,
        "SENT" if envio.ok else ("FAILED_RETRY" if envio.retriable else "FAILED"),
        envio.error, usuario_id=usuario_id,
    )
    return envio


# ---------- Estado del operador (caso activo) ----------
def _set_active_case(db: Session, usuario: Usuario, caso_id: int) -> None:
    fila = db.get(UsuarioCasoActivo, usuario.id)
    if fila is None:
        db.add(UsuarioCasoActivo(usuario_id=usuario.id, caso_id=caso_id))
    else:
        fila.caso_id = caso_id
        fila.updated_at = datetime.utcnow()
    db.commit()


def _clear_active_case(db: Session, usuario: Usuario) -> None:
    fila = db.get(UsuarioCasoActivo, usuario.id)
    if fila is not None:
        db.delete(fila)
        db.commit()


def _get_active_case(db: Session, usuario: Usuario) -> CasoEscalamiento | None:
    fila = db.get(UsuarioCasoActivo, usuario.id)
    if fila is None:
        return None
    if fila.updated_at and datetime.utcnow() - fila.updated_at > timedelta(
        minutes=_ACTIVE_CASE_TTL_MINUTES
    ):
        db.delete(fila)
        db.commit()
        return None
    caso = db.get(CasoEscalamiento, fila.caso_id)
    if caso is None or caso.estado == EstadoCaso.CERRADO:
        db.delete(fila)
        db.commit()
        return None
    return caso


def _case_for_operator_reply(
    db: Session,
    usuario: Usuario,
    chat_id: int,
    reply_to_message_id: int | None,
) -> CasoEscalamiento | None:
    """Resuelve el caso cuando el operador cita un aviso o está en modo chat."""
    if reply_to_message_id is not None:
        fila = db.scalar(
            select(CasoTelegramNotificacion).where(
                CasoTelegramNotificacion.chat_id == str(chat_id),
                CasoTelegramNotificacion.message_id == int(reply_to_message_id),
            )
        )
        if fila is not None:
            caso = db.get(CasoEscalamiento, fila.caso_id)
            if caso is not None and caso.estado != EstadoCaso.CERRADO:
                return caso
    return _get_active_case(db, usuario)


# ---------- Formato de casos / línea de tiempo ----------
def _es_admin(db: Session, usuario: Usuario) -> bool:
    return RolCodigo.ADMIN in _usuario_roles(db, usuario.id)


def _puede_ver_caso(db: Session, usuario: Usuario, caso: CasoEscalamiento) -> bool:
    """Admin ve todo; operador ve sus casos y los libres para reclamarlos."""
    if _es_admin(db, usuario):
        return True
    return caso.responsable_id is None or caso.responsable_id == usuario.id


def _format_caso(db: Session, caso: CasoEscalamiento) -> str:
    pedido = db.get(Pedido, caso.pedido_id)
    cliente = pedido.cliente if pedido else None
    responsable = db.get(Usuario, caso.responsable_id) if caso.responsable_id else None

    lineas = [
        f"📁 Caso #{caso.id} · {caso.motivo.value}",
        f"Estado: {caso.estado.value} · Prioridad: {caso.prioridad.value}",
        f"Responsable: {responsable.nombre_completo if responsable else 'sin asignar'}",
        f"Cliente: {cliente.nombre if cliente else '—'}",
    ]
    if pedido:
        modalidad = (
            pedido.modalidad_entrega.value.replace("_", " ").title()
            if pedido.modalidad_entrega else "—"
        )
        lineas.extend([
            f"Pedido: {pedido.codigo} · {pedido.estado_actual.value}",
            f"Fecha prometida: {pedido.fecha_prometida:%d/%m/%Y}",
            f"Modalidad: {modalidad}",
        ])
    lineas.append(
        "Telegram: "
        + ("vinculado ✅" if cliente and cliente.telegram_chat_id else "sin vincular ⚠️")
    )
    lineas.extend([
        "",
        f"Descripción: {caso.descripcion[:300]}",
        "",
        "🕒 Últimos eventos:",
    ])

    if pedido:
        timeline = build_timeline(
            db, pedido, incluir_mensajes=True, limit=_MAX_TIMELINE_EVENTS
        )
        if not timeline.eventos:
            lineas.append("• Sin eventos registrados.")
        for evento in timeline.eventos:
            icono = _EVENT_ICONS.get(evento.tipo, "•")
            detalle = f" — {evento.detalle[:180]}" if evento.detalle else ""
            lineas.append(
                f"• {evento.fecha:%d/%m %H:%M} {icono} {evento.titulo}{detalle}"
            )
    else:
        lineas.append("• No se encontró el pedido asociado.")

    return "\n".join(lineas)[:4000]


def _format_casos(db: Session, usuario: Usuario) -> str:
    stmt = select(CasoEscalamiento).where(
        CasoEscalamiento.estado.in_([EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO])
    )
    if not _es_admin(db, usuario):
        stmt = stmt.where(
            or_(
                CasoEscalamiento.responsable_id == usuario.id,
                CasoEscalamiento.responsable_id.is_(None),
            )
        )
    casos = db.scalars(
        stmt.order_by(CasoEscalamiento.fecha_apertura.desc()).limit(20)
    ).all()
    if not casos:
        return "✅ No hay casos abiertos o en proceso para ti."

    lineas = [f"📋 Casos activos ({len(casos)}):"]
    for caso in casos:
        pedido = db.get(Pedido, caso.pedido_id)
        cliente = pedido.cliente if pedido else None
        responsable = (
            db.get(Usuario, caso.responsable_id) if caso.responsable_id else None
        )
        lineas.append(
            f"#{caso.id} · {caso.motivo.value} · {caso.prioridad.value} · "
            f"{pedido.codigo if pedido else '—'} · "
            f"{cliente.nombre if cliente else '—'} · {caso.estado.value} · "
            f"👤 {responsable.nombre_completo if responsable else 'sin asignar'}"
        )
    lineas.extend(["", "Usa /caso <id> para ver el detalle y la línea de tiempo."])
    return "\n".join(lineas)[:4000]


# ---------- Comandos y respuesta de operadores ----------
def _parse_caso_id(args: str) -> int | None:
    first = args.split(maxsplit=1)[0] if args else ""
    return int(first) if first.isdigit() else None


def _handle_operator_command(
    db: Session,
    tg: TelegramService,
    chat_id: int,
    text: str,
    usuario: Usuario,
    external_id: str | None,
) -> dict[str, Any] | None:
    if _command_args(text, "/casos") is not None:
        _log_comando(
            db, chat_id, "/casos", None, None, external_id,
            usuario_id=usuario.id,
        )
        _reply(
            db, tg, chat_id, _format_casos(db, usuario), usuario_id=usuario.id,
        )
        return {"handled": "operator_cases", "chat_id": chat_id}

    args = _command_args(text, "/caso")
    if args is not None:
        _log_comando(
            db, chat_id, "/caso [id]", None, None, external_id,
            usuario_id=usuario.id,
        )
        caso_id = _parse_caso_id(args)
        if caso_id is None:
            _reply(
                db, tg, chat_id, _OPERATOR_COMMAND_HELP["/caso"],
                usuario_id=usuario.id,
            )
            return {"handled": "operator_case_help", "chat_id": chat_id}
        caso = db.get(CasoEscalamiento, caso_id)
        if caso is None:
            _reply(
                db, tg, chat_id, f"No encontré el caso #{caso_id}.",
                usuario_id=usuario.id,
            )
            return {"handled": "operator_case_not_found", "chat_id": chat_id}
        if not _puede_ver_caso(db, usuario, caso):
            responsable = (
                db.get(Usuario, caso.responsable_id)
                if caso.responsable_id else None
            )
            _reply(
                db, tg, chat_id,
                f"⚠️ El caso #{caso.id} está asignado a "
                f"{responsable.nombre_completo if responsable else 'otro operador'}.",
                usuario_id=usuario.id,
            )
            return {"handled": "operator_case_denied", "chat_id": chat_id}
        _reply(
            db, tg, chat_id, _format_caso(db, caso), usuario_id=usuario.id,
        )
        return {"handled": "operator_case", "chat_id": chat_id, "caso_id": caso_id}

    args = _command_args(text, "/responder")
    if args is not None:
        _log_comando(
            db, chat_id, "/responder [id] [mensaje]", None, None, external_id,
            usuario_id=usuario.id,
        )
        partes = args.split(maxsplit=1)
        if len(partes) < 2 or not partes[0].isdigit() or not partes[1].strip():
            _reply(
                db, tg, chat_id, _OPERATOR_COMMAND_HELP["/responder"],
                usuario_id=usuario.id,
            )
            return {"handled": "operator_reply_help", "chat_id": chat_id}
        caso_id = int(partes[0])
        contenido = partes[1].strip()
        return _send_operator_reply(db, tg, chat_id, usuario, caso_id, contenido)

    args = _command_args(text, "/cerrar")
    if args is not None:
        _log_comando(
            db, chat_id, "/cerrar [id]", None, None, external_id,
            usuario_id=usuario.id,
        )
        caso_id = _parse_caso_id(args)
        if caso_id is None:
            _reply(
                db, tg, chat_id, _OPERATOR_COMMAND_HELP["/cerrar"],
                usuario_id=usuario.id,
            )
            return {"handled": "operator_close_help", "chat_id": chat_id}
        return _close_case(db, tg, chat_id, usuario, caso_id)

    args = _command_args(text, "/liberar")
    if args is not None:
        _log_comando(
            db, chat_id, "/liberar [id]", None, None, external_id,
            usuario_id=usuario.id,
        )
        caso_id = _parse_caso_id(args)
        if caso_id is None:
            _reply(
                db, tg, chat_id, _OPERATOR_COMMAND_HELP["/liberar"],
                usuario_id=usuario.id,
            )
            return {"handled": "operator_release_help", "chat_id": chat_id}
        return _release_case(db, tg, chat_id, usuario, caso_id)

    if _command_args(text, "/salir") is not None:
        _log_comando(
            db, chat_id, "/salir", None, None, external_id,
            usuario_id=usuario.id,
        )
        _clear_active_case(db, usuario)
        _reply(
            db, tg, chat_id,
            "✅ Saliste del modo respuesta. Usa /casos para volver.",
            usuario_id=usuario.id,
        )
        return {"handled": "operator_exit", "chat_id": chat_id}

    return None


def _send_operator_reply(
    db: Session,
    tg: TelegramService,
    chat_id: int,
    usuario: Usuario,
    caso_id: int,
    contenido: str,
) -> dict[str, Any]:
    try:
        caso, com, envio = responder_caso(
            db,
            caso_id,
            contenido,
            usuario_id=usuario.id,
            telegram=tg,
            es_admin=_es_admin(db, usuario),
        )
    except CasoError as exc:
        _reply(
            db, tg, chat_id, f"⚠️ {exc.message}", usuario_id=usuario.id,
        )
        return {
            "handled": "operator_reply_rejected",
            "chat_id": chat_id,
            "code": exc.code,
        }

    _set_active_case(db, usuario, caso.id)
    pedido = db.get(Pedido, caso.pedido_id)
    cliente = pedido.cliente if pedido else None
    if envio.ok:
        _reply(
            db, tg, chat_id,
            f"✅ Enviado a {cliente.nombre if cliente else 'el cliente'} · "
            f"Caso #{caso.id}.\n"
            "Puedes seguir escribiendo para responder al mismo caso o usar /salir.",
            usuario_id=usuario.id,
        )
    else:
        _reply(
            db, tg, chat_id,
            f"⚠️ El mensaje quedó registrado pero no se pudo entregar: "
            f"{envio.error or 'error desconocido'}\n"
            "Revisa la vinculación de Telegram del cliente e inténtalo de nuevo.",
            usuario_id=usuario.id,
        )
    return {
        "handled": "operator_replied",
        "chat_id": chat_id,
        "caso_id": caso.id,
        "sent": envio.ok,
        "comunicacion_id": com.id,
    }


def _close_case(
    db: Session,
    tg: TelegramService,
    chat_id: int,
    usuario: Usuario,
    caso_id: int,
) -> dict[str, Any]:
    try:
        caso, _com = cerrar_caso(
            db,
            caso_id,
            usuario_id=usuario.id,
            telegram=tg,
            es_admin=_es_admin(db, usuario),
        )
    except CasoError as exc:
        _reply(
            db, tg, chat_id, f"⚠️ {exc.message}", usuario_id=usuario.id,
        )
        return {
            "handled": "operator_close_rejected",
            "chat_id": chat_id,
            "code": exc.code,
        }

    _clear_active_case(db, usuario)
    _reply(
        db, tg, chat_id, f"✅ Caso #{caso.id} cerrado.",
        usuario_id=usuario.id,
    )
    return {"handled": "operator_closed", "chat_id": chat_id, "caso_id": caso.id}


def _release_case(
    db: Session,
    tg: TelegramService,
    chat_id: int,
    usuario: Usuario,
    caso_id: int,
) -> dict[str, Any]:
    try:
        caso, _com = reasignar_caso(
            db,
            caso_id,
            None,
            usuario_id=usuario.id,
            es_admin=_es_admin(db, usuario),
        )
    except CasoError as exc:
        _reply(
            db, tg, chat_id, f"⚠️ {exc.message}", usuario_id=usuario.id,
        )
        return {
            "handled": "operator_release_rejected",
            "chat_id": chat_id,
            "code": exc.code,
        }

    _clear_active_case(db, usuario)
    _reply(
        db, tg, chat_id,
        f"🔓 Caso #{caso.id} liberado. Queda sin asignar para que otro "
        "operador lo tome.",
        usuario_id=usuario.id,
    )
    return {"handled": "operator_released", "chat_id": chat_id, "caso_id": caso.id}


# ---------- Notificación al operador ----------
def _operator_recipients(
    db: Session | None, fallback: str | None
) -> list[tuple[str, int | None]]:
    """Pares (chat_id, usuario_id) de operadores activos + fallback de .env."""
    destinatarios: list[tuple[str, int | None]] = []
    if db is not None:
        filas = db.execute(
            select(Usuario.telegram_chat_id, Usuario.id)
            .join(UsuarioRol, UsuarioRol.usuario_id == Usuario.id)
            .join(Rol, Rol.id == UsuarioRol.rol_id)
            .where(
                Usuario.activo == True,  # noqa: E712
                Usuario.telegram_chat_id.is_not(None),
                Rol.codigo.in_(list(_OPERATOR_ROLES)),
            )
        ).all()
        destinatarios.extend((str(chat), int(uid)) for chat, uid in filas if chat)
    if fallback:
        destinatarios.append((str(fallback), None))

    vistos: set[str] = set()
    unicos: list[tuple[str, int | None]] = []
    for chat, uid in destinatarios:
        if chat not in vistos:
            vistos.add(chat)
            unicos.append((chat, uid))
    return unicos


def _case_reply_markup(caso_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "📄 Ver caso", "callback_data": f"caso:{caso_id}:ver"},
                {"text": "💬 Responder", "callback_data": f"caso:{caso_id}:responder"},
            ],
            [
                {"text": "✅ Cerrar caso", "callback_data": f"caso:{caso_id}:cerrar"},
            ],
        ]
    }


def _client_message_markup(caso_id: int) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "💬 Responder", "callback_data": f"caso:{caso_id}:responder"},
                {"text": "📄 Ver caso", "callback_data": f"caso:{caso_id}:ver"},
            ],
        ]
    }


def _resolve_caso_abierto(db: Session, pedido: Pedido) -> CasoEscalamiento | None:
    return db.scalar(
        select(CasoEscalamiento)
        .where(
            CasoEscalamiento.pedido_id == pedido.id,
            CasoEscalamiento.estado.in_([EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]),
        )
        .order_by(CasoEscalamiento.fecha_apertura.desc())
        .limit(1)
    )


def _case_recipients(
    db: Session, caso: CasoEscalamiento, tg: TelegramService
) -> list[tuple[str, int | None]]:
    """Responsable si está vinculado; si no, todos los operadores."""
    if caso.responsable_id is not None:
        responsable = db.get(Usuario, caso.responsable_id)
        if responsable and responsable.activo and responsable.telegram_chat_id:
            return [(str(responsable.telegram_chat_id), responsable.id)]
    return _operator_recipients(db, tg.operator_chat_id)


def _forward_client_message_to_case(
    db: Session,
    tg: TelegramService,
    cliente: Cliente,
    pedido: Pedido,
    caso: CasoEscalamiento,
    contenido: str,
    external_id: str | None,
) -> dict[str, Any] | None:
    """Reenvía el mensaje del cliente al operador que atiende el caso.

    Devuelve None si no hay ningún operador vinculado: en ese caso el
    llamador deja que el agente responda normalmente.
    """
    destinatarios = [
        (chat, uid)
        for chat, uid in _case_recipients(db, caso, tg)
        if not cliente.telegram_chat_id or chat != str(cliente.telegram_chat_id)
    ]
    if not destinatarios:
        return None

    # Mensaje entrante visible en la línea de tiempo del pedido.
    com = Comunicacion(
        pedido_id=pedido.id,
        direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.TELEGRAM,
        contenido=contenido,
        autor=AutorComunicacion.CLIENTE,
        clase=ClaseComunicacion.CLIENTE,
        escalado=True,
        caso_id=caso.id,
        whatsapp_message_id=external_id,
        fecha=datetime.utcnow(),
    )
    db.add(com)
    db.commit()
    db.refresh(com)

    texto = (
        f"💬 Mensaje del cliente · Caso #{caso.id}\n"
        f"Pedido: {pedido.codigo}\n"
        f"Cliente: {cliente.nombre}\n"
        f"Mensaje: {contenido[:1500]}\n\n"
        "Responde citando este mensaje o pulsa el botón."
    )
    reply_markup = _client_message_markup(caso.id)
    mappings: list[CasoTelegramNotificacion] = []
    operativos: list[Comunicacion] = []
    enviados = 0
    for chat_id, usuario_id in destinatarios:
        envio = tg.send_message(chat_id, texto, reply_markup=reply_markup)
        estado_entrega = "SENT" if envio.ok else (
            "FAILED_RETRY" if envio.retriable else "FAILED"
        )
        # Se audita también el intento fallido: todo aviso interno queda
        # registrado como OPERATIVO.
        operativos.append(Comunicacion(
            pedido_id=pedido.id,
            direccion=DireccionComunicacion.SALIENTE,
            canal=Canal.TELEGRAM,
            contenido=texto,
            autor=AutorComunicacion.AGENTE,
            clase=ClaseComunicacion.OPERATIVO,
            usuario_id=usuario_id,
            escalado=False,
            caso_id=caso.id,
            estado_entrega=estado_entrega,
            error_envio=(
                (envio.error or "")[:500] if not envio.ok else None
            ),
            enviado_en=datetime.utcnow() if envio.ok else None,
            fecha=datetime.utcnow(),
        ))
        if not envio.ok:
            logger.warning(
                "client_message_forward_failed caso_id=%s chat_id=%s err=%s",
                caso.id, chat_id, tg.redact(envio.error or "unknown"),
            )
            continue
        enviados += 1
        if envio.message_id:
            mappings.append(CasoTelegramNotificacion(
                caso_id=caso.id,
                usuario_id=usuario_id,
                chat_id=str(chat_id),
                message_id=int(envio.message_id),
            ))

    if mappings or operativos:
        try:
            if operativos:
                db.add_all(operativos)
            if mappings:
                db.add_all(mappings)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "client_message_mapping_failed caso_id=%s", caso.id,
            )

    return {
        "handled": "case_message_forwarded",
        "caso_id": caso.id,
        "chat_id": int(cliente.telegram_chat_id or 0),
        "forwarded": enviados,
        "comunicacion_id": com.id,
    }


def notify_operator_new_caso(
    caso: CasoEscalamiento,
    pedido: Pedido,
    telegram: TelegramService | None = None,
    db: Session | None = None,
) -> None:
    tg = telegram or TelegramService()
    if not tg.enabled:
        logger.info(
            "operator_notification_skipped caso_id=%s (telegram_disabled)", caso.id,
        )
        return

    destinatarios = _operator_recipients(db, tg.operator_chat_id)
    if not destinatarios:
        logger.info(
            "operator_notification_skipped caso_id=%s (sin destinatarios)", caso.id,
        )
        return

    text = (
        f"🚨 Nuevo caso #{caso.id} · {caso.motivo.value}\n"
        f"Pedido: {pedido.codigo}\n"
        f"Prioridad: {caso.prioridad.value}\n"
        f"Cliente: {pedido.cliente.nombre}\n"
        f"Descripción: {caso.descripcion[:200]}\n\n"
        "Pulsa un botón o responde citando este mensaje para atender el caso."
    )
    reply_markup = _case_reply_markup(caso.id)

    mappings: list[CasoTelegramNotificacion] = []
    operativos: list[Comunicacion] = []
    for chat_id, usuario_id in destinatarios:
        envio = tg.send_message(chat_id, text, reply_markup=reply_markup)
        estado_entrega = "SENT" if envio.ok else (
            "FAILED_RETRY" if envio.retriable else "FAILED"
        )
        # Los dobles de prueba usan SimpleNamespace; sólo persistimos con
        # casos reales para no violar la FK.
        if isinstance(caso, CasoEscalamiento) and db is not None:
            # También se audita el intento fallido: todo aviso interno queda
            # registrado como OPERATIVO.
            operativos.append(Comunicacion(
                pedido_id=pedido.id,
                direccion=DireccionComunicacion.SALIENTE,
                canal=Canal.TELEGRAM,
                contenido=text,
                autor=AutorComunicacion.AGENTE,
                clase=ClaseComunicacion.OPERATIVO,
                usuario_id=usuario_id,
                escalado=False,
                caso_id=caso.id,
                estado_entrega=estado_entrega,
                error_envio=(
                    (envio.error or "")[:500] if not envio.ok else None
                ),
                enviado_en=datetime.utcnow() if envio.ok else None,
                fecha=datetime.utcnow(),
            ))
        if not envio.ok:
            logger.warning(
                "operator_notification_failed caso_id=%s chat_id=%s err=%s",
                caso.id, chat_id, tg.redact(envio.error or "unknown"),
            )
            continue
        if isinstance(caso, CasoEscalamiento) and db is not None and envio.message_id:
            mappings.append(
                CasoTelegramNotificacion(
                    caso_id=caso.id,
                    usuario_id=usuario_id,
                    chat_id=str(chat_id),
                    message_id=int(envio.message_id),
                )
            )

    if db is not None and (mappings or operativos):
        try:
            if operativos:
                db.add_all(operativos)
            if mappings:
                db.add_all(mappings)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "operator_notification_mapping_failed caso_id=%s", caso.id,
            )


def notify_caso_reasignado(
    db: Session,
    caso: CasoEscalamiento,
    pedido: Pedido,
    *,
    actor_id: int,
    telegram: TelegramService | None = None,
) -> bool:
    """Avisa por Telegram al nuevo responsable de un caso reasignado.

    Devuelve True si no hacía falta avisar (autoasignación) o si el mensaje
    salió. Devuelve False si el responsable no tiene Telegram o el envío
    falló; la asignación ya está guardada y no se revierte.
    """
    if caso.responsable_id is None or caso.responsable_id == actor_id:
        return True

    tg = telegram or TelegramService()
    if not tg.enabled:
        return False
    responsable = db.get(Usuario, caso.responsable_id)
    if (
        responsable is None
        or not responsable.activo
        or not responsable.telegram_chat_id
    ):
        return False
    chat_id = str(responsable.telegram_chat_id)
    cliente = pedido.cliente
    if cliente and cliente.telegram_chat_id and str(cliente.telegram_chat_id) == chat_id:
        return False

    actor = db.get(Usuario, actor_id)
    text = (
        f"🔁 Caso #{caso.id} reasignado a ti\n"
        f"Por: {actor.nombre_completo if actor else 'un administrador'}\n"
        f"Pedido: {pedido.codigo}\n"
        f"Cliente: {cliente.nombre if cliente else '—'}\n"
        f"Motivo: {caso.motivo.value} · Prioridad: {caso.prioridad.value}\n\n"
        "Pulsa Responder o usa /caso para ver el detalle."
    )
    envio = tg.send_message(
        chat_id, text, reply_markup=_case_reply_markup(caso.id),
    )
    estado_entrega = "SENT" if envio.ok else (
        "FAILED_RETRY" if envio.retriable else "FAILED"
    )
    db.add(Comunicacion(
        pedido_id=pedido.id,
        direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.TELEGRAM,
        contenido=text,
        autor=AutorComunicacion.AGENTE,
        clase=ClaseComunicacion.OPERATIVO,
        usuario_id=responsable.id,
        escalado=False,
        caso_id=caso.id,
        estado_entrega=estado_entrega,
        error_envio=(envio.error or "")[:500] if not envio.ok else None,
        enviado_en=datetime.utcnow() if envio.ok else None,
        fecha=datetime.utcnow(),
    ))
    if envio.ok and envio.message_id:
        db.add(CasoTelegramNotificacion(
            caso_id=caso.id,
            usuario_id=responsable.id,
            chat_id=chat_id,
            message_id=int(envio.message_id),
        ))
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("reassignment_notification_persist_failed caso_id=%s", caso.id)
    return bool(envio.ok)


# =========================================================================
# Callback queries (botones inline)
# =========================================================================
def handle_telegram_callback(
    db: Session,
    update: dict[str, Any],
    telegram: TelegramService | None = None,
) -> dict[str, Any]:
    tg = telegram or TelegramService()
    cq = _callback(update)
    cq_id = str(cq.get("id") or "")
    chat_id = _callback_chat_id(update)
    data = str(cq.get("data") or "")

    usuario = _resolve_operador(db, chat_id)
    if usuario is None:
        tg.answer_callback_query(
            cq_id,
            "Vincula tu cuenta con /vincular <email> <contraseña> para atender casos.",
            show_alert=True,
        )
        return {"handled": "callback_unauthorized", "chat_id": chat_id}

    partes = data.split(":")
    if len(partes) != 3 or partes[0] != "caso" or not partes[1].isdigit():
        tg.answer_callback_query(cq_id, "Acción no reconocida.")
        return {"handled": "callback_invalid", "chat_id": chat_id}

    caso_id = int(partes[1])
    accion = partes[2]
    es_admin = _es_admin(db, usuario)
    caso = db.get(CasoEscalamiento, caso_id)
    if caso is None:
        tg.answer_callback_query(cq_id, f"No encontré el caso #{caso_id}.", show_alert=True)
        return {"handled": "callback_case_not_found", "chat_id": chat_id}

    if not _puede_ver_caso(db, usuario, caso):
        tg.answer_callback_query(
            cq_id,
            "Este caso está asignado a otro operador.",
            show_alert=True,
        )
        return {"handled": "callback_case_denied", "chat_id": chat_id}

    if accion == "ver":
        tg.answer_callback_query(cq_id, f"Caso #{caso.id}")
        _reply(db, tg, chat_id, _format_caso(db, caso))
        return {"handled": "callback_case_view", "chat_id": chat_id, "caso_id": caso.id}

    if accion == "responder":
        if caso.estado == EstadoCaso.CERRADO:
            tg.answer_callback_query(cq_id, "El caso ya está cerrado.", show_alert=True)
            return {"handled": "callback_case_closed", "chat_id": chat_id}
        if (
            not es_admin
            and caso.responsable_id
            and caso.responsable_id != usuario.id
        ):
            tg.answer_callback_query(
                cq_id,
                "El caso ya está siendo atendido por otro operador.",
                show_alert=True,
            )
            return {"handled": "callback_case_assigned", "chat_id": chat_id}
        _set_active_case(db, usuario, caso.id)
        tg.answer_callback_query(cq_id, f"Caso #{caso.id} activo")
        _reply(
            db, tg, chat_id,
            f"💬 Caso #{caso.id} activo. Escribe tu respuesta y la enviaré al "
            "cliente.\nUsa /salir para terminar.",
        )
        return {"handled": "callback_case_reply", "chat_id": chat_id, "caso_id": caso.id}

    if accion == "cerrar":
        resultado = _close_case(db, tg, chat_id, usuario, caso.id)
        if resultado["handled"] == "operator_closed":
            tg.answer_callback_query(cq_id, f"Caso #{caso.id} cerrado")
        else:
            tg.answer_callback_query(cq_id, "No se pudo cerrar el caso.", show_alert=True)
        return resultado

    tg.answer_callback_query(cq_id, "Acción no reconocida.")
    return {"handled": "callback_invalid", "chat_id": chat_id}


# =========================================================================
# Punto de entrada (usado por webhook y por polling)
# =========================================================================
def handle_telegram_update(
    db: Session,
    update: dict[str, Any],
    telegram: TelegramService | None = None,
) -> dict[str, Any]:
    tg = telegram or TelegramService()

    if update.get("callback_query"):
        return handle_telegram_callback(db, update, telegram=tg)

    uid = _update_id(update)
    chat_id = _chat_id(update)
    text = _text(update)
    external_id = _external_id(uid)

    if chat_id is None or text is None:
        return {"skipped": True, "reason": "non_text_update", "update_id": uid}

    # Deduplicación por update_id
    if external_id:
        if db.scalar(
            select(Comunicacion.id).where(
                Comunicacion.whatsapp_message_id == external_id
            )
        ):
            return {"skipped": True, "reason": "duplicate", "update_id": uid}

    cliente = _resolve_cliente(db, chat_id)
    operador = _resolve_operador(db, chat_id)
    pedido: Pedido | None = None

    # ---------- Comandos básicos (con trazabilidad) ----------
    if text.startswith("/start"):
        _log_comando(db, chat_id, text, cliente, pedido, external_id)
        envio = tg.send_message(chat_id, _WELCOME)
        _log_saliente_comando(
            db, chat_id, _WELCOME, cliente, pedido,
            "SENT" if envio.ok else ("FAILED_RETRY" if envio.retriable else "FAILED"),
            envio.error,
        )
        return {"handled": "start", "chat_id": chat_id, "sent": envio.ok}

    if text.startswith("/whoami"):
        _log_comando(db, chat_id, text, cliente, pedido, external_id)
        msg = (
            f"Tu chat_id de Telegram es: `{chat_id}`\n\n"
            "Si eres operador, usa /vincular <email> <contraseña> para recibir "
            "notificaciones de casos."
        )
        envio = tg.send_message(chat_id, msg, parse_mode="Markdown")
        _log_saliente_comando(
            db, chat_id, msg, cliente, pedido,
            "SENT" if envio.ok else ("FAILED_RETRY" if envio.retriable else "FAILED"),
            envio.error,
        )
        return {"handled": "whoami", "chat_id": chat_id, "sent": envio.ok}

    # ---------- Operadores: vinculación por credenciales ----------
    args_vincular = _command_args(text, "/vincular")
    if args_vincular is not None:
        return _link_operator(db, tg, chat_id, args_vincular, external_id)

    if _command_args(text, "/desvincular") is not None:
        return _unlink_operator(db, tg, chat_id, external_id)

    # ---------- Comandos de operador ----------
    if operador is not None:
        resultado = _handle_operator_command(
            db, tg, chat_id, text, operador, external_id
        )
        if resultado is not None:
            return resultado

        # Responder citando un aviso o en modo conversación.
        if _reply_to_message_id(update) is not None or _get_active_case(db, operador):
            caso = _case_for_operator_reply(
                db, operador, chat_id, _reply_to_message_id(update)
            )
            if caso is not None:
                return _send_operator_reply(
                    db, tg, chat_id, operador, caso.id, text.strip()
                )

    # ---------- Vinculación por código de pedido + DNI ----------
    if cliente:
        pedido = _resolve_pedido_activo(db, cliente)
    else:
        codigo, documento = _parse_pedido_link(text)
        if codigo:
            # No persistimos el DNI en el historial de mensajes (dato personal).
            contenido_log = f"{codigo} [DNI]" if documento else text
            _log_comando(db, chat_id, contenido_log, None, None, external_id)

            if documento is None:
                _reply(db, tg, chat_id, _LINK_DNI_REQUIRED)
                return {"handled": "dni_required", "chat_id": chat_id}

            p = _find_pedido_by_codigo(db, codigo)
            if p is None or not _documento_matches(p.cliente, documento):
                # Mensaje genérico: no revelamos si el pedido existe o no.
                _reply(db, tg, chat_id, _LINK_INVALID)
                return {"handled": "link_rejected", "chat_id": chat_id}

            actual = p.cliente.telegram_chat_id
            if actual and actual != str(chat_id):
                _reply(db, tg, chat_id, _LINK_ALREADY_LINKED)
                return {"handled": "already_linked", "chat_id": chat_id}

            p.cliente.telegram_chat_id = str(chat_id)
            db.commit()
            cliente = p.cliente
            pedido = p

            msg = f"✅ Vinculado al pedido {p.codigo}. Ya puedes consultar su estado."
            _reply(db, tg, chat_id, msg, cliente, pedido)
            return {"handled": "vinculado", "chat_id": chat_id, "pedido_id": p.id}

    # ---------- Caso abierto: el mensaje va al operador (chat humano) ----------
    if cliente and pedido:
        caso_abierto = _resolve_caso_abierto(db, pedido)
        if caso_abierto is not None:
            forward = _forward_client_message_to_case(
                db, tg, cliente, pedido, caso_abierto, text, external_id,
            )
            if forward is not None:
                return forward

    if not cliente:
        if es_consulta_conocida(text):
            result = AgentService(db).handle_incoming_message(
                IncomingMessage(
                    canal=Canal.TELEGRAM,
                    contenido=text,
                    whatsapp_message_id=external_id,
                )
            )
            if result.response_text:
                _reply(db, tg, chat_id, result.response_text)
                return {
                    "handled": "knowledge_answer",
                    "chat_id": chat_id,
                    "intent": result.classification.intent,
                }
        _log_comando(db, chat_id, text, None, None, external_id)
        if operador is not None:
            _reply(db, tg, chat_id, _OPERATOR_HELP)
            return {"handled": "operator_help", "chat_id": chat_id}
        msg = (
            "No encontré un pedido asociado a tu cuenta de Telegram.\n"
            "Envíame tu código de pedido junto con tu DNI para vincularlo.\n"
            "Ejemplo: PD-2025-0001 70000001"
        )
        _reply(db, tg, chat_id, msg)
        return {"handled": "no_cliente", "chat_id": chat_id}

    # ---------- Procesar con el agente (reutiliza toda la lógica) ----------
    agente = AgentService(db)
    result = agente.handle_incoming_message(
        IncomingMessage(
            pedido_id=pedido.id if pedido else None,
            cliente_id=cliente.id,
            canal=Canal.TELEGRAM,
            contenido=text,
            whatsapp_message_id=external_id,
        )
    )

    # ---------- Enviar respuesta por Telegram ----------
    if result.response_text:
        envio = tg.send_message(chat_id, result.response_text)
        if result.outgoing_comunicacion_id:
            com_out = db.get(Comunicacion, result.outgoing_comunicacion_id)
            if com_out:
                com_out.canal = Canal.TELEGRAM
                if envio.ok:
                    com_out.estado_entrega = "SENT"
                    com_out.enviado_en = datetime.utcnow()
                    com_out.error_envio = None
                else:
                    com_out.estado_entrega = (
                        "FAILED_RETRY" if envio.retriable else "FAILED"
                    )
                    com_out.error_envio = (envio.error or "unknown")[:500]
                db.commit()

    # ---------- Notificar al operador si se escaló ----------
    if result.escalated and result.caso_id and pedido:
        caso = db.get(CasoEscalamiento, result.caso_id)
        if caso:
            notify_operator_new_caso(caso, pedido, telegram=tg, db=db)

    return {
        "handled": "message",
        "chat_id": chat_id,
        "escalated": result.escalated,
        "caso_id": result.caso_id,
        "intent": result.classification.intent,
    }

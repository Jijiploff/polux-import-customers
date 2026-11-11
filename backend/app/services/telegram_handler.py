"""Procesa updates de Telegram reutilizando AgentService + RuleEngine.

- Registra todas las entradas (incluidos comandos) en `comunicacion`.
- Envía la respuesta por Telegram y actualiza `estado_entrega`.
- Si el agente escala, crea el caso (ya lo hace AgentService) y notifica
  al operador por Telegram.
"""
from __future__ import annotations

import hmac
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import (
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    Pedido,
)
from app.schemas.agent import IncomingMessage
from app.services.agent_service import AgentService
from app.services.telegram_service import TelegramService

logger = get_logger("telegram_handler")

_WELCOME = (
    "👋 Bienvenido a Polux Import.\n\n"
    "Para consultar el estado de tu pedido, envíame tu código junto con tu DNI "
    "(por ejemplo: PD-2025-0001 70000001).\n\n"
    "Si necesitas hablar con un asesor, escribe tu consulta y te derivaré."
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


# ---------- Persistencia de comandos (trazabilidad) ----------
def _log_comando(
    db: Session,
    chat_id: int,
    contenido: str,
    cliente: Cliente | None,
    pedido: Pedido | None,
    external_id: str | None,
) -> Comunicacion:
    com = Comunicacion(
        pedido_id=pedido.id if pedido else None,
        direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.TELEGRAM,
        contenido=contenido,
        autor=AutorComunicacion.CLIENTE,
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
) -> Comunicacion:
    com = Comunicacion(
        pedido_id=pedido.id if pedido else None,
        direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.TELEGRAM,
        contenido=contenido,
        autor=AutorComunicacion.AGENTE,
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
):
    """Envía una respuesta y la registra en `comunicacion`."""
    envio = tg.send_message(chat_id, contenido)
    _log_saliente_comando(
        db, chat_id, contenido, cliente, pedido,
        "SENT" if envio.ok else ("FAILED_RETRY" if envio.retriable else "FAILED"),
        envio.error,
    )
    return envio


# ---------- Notificación al operador ----------
def notify_operator_new_caso(
    caso: CasoEscalamiento, pedido: Pedido, telegram: TelegramService | None = None
) -> None:
    tg = telegram or TelegramService()
    if not tg.enabled or not tg.operator_chat_id:
        logger.info("operator_notification_skipped caso_id=%s (no chat_id)", caso.id)
        return
    text = (
        f"🚨 Nuevo caso #{caso.id} · {caso.motivo.value}\n"
        f"Pedido: {pedido.codigo}\n"
        f"Prioridad: {caso.prioridad.value}\n"
        f"Cliente: {pedido.cliente.nombre}\n"
        f"Descripción: {caso.descripcion[:200]}"
    )
    tg.send_message(tg.operator_chat_id, text)


# =========================================================================
# Punto de entrada (usado por webhook y por polling)
# =========================================================================
def handle_telegram_update(
    db: Session,
    update: dict[str, Any],
    telegram: TelegramService | None = None,
) -> dict[str, Any]:
    tg = telegram or TelegramService()
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
    pedido: Pedido | None = None

    # ---------- Comandos (con trazabilidad) ----------
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
            "Envíalo al administrador para recibir notificaciones de casos."
        )
        envio = tg.send_message(chat_id, msg, parse_mode="Markdown")
        _log_saliente_comando(
            db, chat_id, msg, cliente, pedido,
            "SENT" if envio.ok else ("FAILED_RETRY" if envio.retriable else "FAILED"),
            envio.error,
        )
        return {"handled": "whoami", "chat_id": chat_id, "sent": envio.ok}

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

    if not cliente:
        msg = (
            "No encontré un pedido asociado a tu cuenta de Telegram.\n"
            "Envíame tu código de pedido junto con tu DNI para vincularlo.\n"
            "Ejemplo: PD-2025-0001 70000001"
        )
        _log_comando(db, chat_id, text, None, None, external_id)
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
            notify_operator_new_caso(caso, pedido, telegram=tg)

    return {
        "handled": "message",
        "chat_id": chat_id,
        "escalated": result.escalated,
        "caso_id": result.caso_id,
        "intent": result.classification.intent,
    }
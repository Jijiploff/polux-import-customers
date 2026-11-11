"""Gestión de casos de escalamiento: primera acción, respuesta y cierre."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import (
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    Comunicacion,
    DireccionComunicacion,
    EstadoCaso,
    Pedido,
    Usuario,
)
from app.schemas.comms import CasoCreate, CasoUpdate
from app.services.telegram_service import TelegramSendResult, TelegramService

logger = get_logger("caso_service")


class CasoError(Exception):
    """Error de negocio reutilizable por el bot y por la API."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def crear_caso(db: Session, payload: CasoCreate, *, usuario_id: int) -> CasoEscalamiento:
    caso = CasoEscalamiento(
        pedido_id=payload.pedido_id,
        motivo=payload.motivo,
        prioridad=payload.prioridad,
        descripcion=payload.descripcion,
        fecha_apertura=datetime.utcnow(),
        estado=EstadoCaso.ABIERTO,
        created_by_id=usuario_id,
        updated_by_id=usuario_id,
    )
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


def actualizar_caso(
    db: Session, caso_id: int, payload: CasoUpdate, *, usuario_id: int
) -> CasoEscalamiento:
    caso = db.get(CasoEscalamiento, caso_id)
    if caso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")
    if caso.estado == EstadoCaso.CERRADO:
        raise HTTPException(status.HTTP_409_CONFLICT, "El caso ya está cerrado")

    if payload.registrar_primera_accion and caso.fecha_primera_accion is None:
        caso.fecha_primera_accion = datetime.utcnow()
        if caso.estado == EstadoCaso.ABIERTO:
            caso.estado = EstadoCaso.EN_PROCESO

    if payload.responsable_id is not None:
        caso.responsable_id = payload.responsable_id

    if payload.estado is not None:
        # Regla: no cerrar sin primera acción (trazabilidad mínima)
        if payload.estado == EstadoCaso.CERRADO:
            if caso.fecha_primera_accion is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "No se puede cerrar un caso sin registrar la primera acción humana",
                )
            caso.fecha_cierre = datetime.utcnow()
        caso.estado = payload.estado

    caso.updated_by_id = usuario_id
    db.commit()
    db.refresh(caso)
    return caso


# =========================================================================
# Respuesta humana por Telegram
# =========================================================================
def _nombre_usuario(db: Session, usuario_id: int | None) -> str:
    if usuario_id is None:
        return "otro operador"
    usuario = db.get(Usuario, usuario_id)
    return usuario.nombre_completo if usuario else "otro operador"


def _crear_y_enviar(
    db: Session,
    pedido: Pedido,
    contenido: str,
    *,
    usuario_id: int,
    caso_id: int | None,
    telegram: TelegramService | None,
) -> tuple[Comunicacion, TelegramSendResult]:
    """Registra la comunicación HUMANO/saliente y la entrega por Telegram.

    Si el cliente no tiene un chat vinculado se lanza `CasoError` para que
    el operador reciba un mensaje claro (no se inventa un envío por WhatsApp).
    """
    cliente = pedido.cliente
    chat_id = cliente.telegram_chat_id if cliente is not None else None
    if not chat_id:
        raise CasoError(
            "sin_telegram",
            "El cliente no tiene Telegram vinculado. Pídele que envíe su "
            "código de pedido junto con su DNI para vincular el chat.",
        )

    tg = telegram or TelegramService()
    com = Comunicacion(
        pedido_id=pedido.id,
        direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.TELEGRAM,
        contenido=contenido,
        autor=AutorComunicacion.HUMANO,
        escalado=caso_id is not None,
        caso_id=caso_id,
        usuario_id=usuario_id,
        estado_entrega="PENDING",
        fecha=datetime.utcnow(),
        created_by_id=usuario_id,
        updated_by_id=usuario_id,
    )
    db.add(com)
    db.flush()

    envio = tg.send_message(chat_id, contenido)
    if envio.ok:
        com.estado_entrega = "SENT"
        com.enviado_en = datetime.utcnow()
        com.error_envio = None
    else:
        com.estado_entrega = "FAILED_RETRY" if envio.retriable else "FAILED"
        com.error_envio = (envio.error or "unknown")[:500]

    return com, envio


def responder_caso(
    db: Session,
    caso_id: int,
    contenido: str,
    *,
    usuario_id: int,
    telegram: TelegramService | None = None,
) -> tuple[CasoEscalamiento, Comunicacion, TelegramSendResult]:
    """Responde un caso desde Telegram y lo envía al cliente.

    El primer operador que responde queda como responsable. Si el caso ya
    fue tomado por otro, se rechaza para evitar respuestas duplicadas.
    """
    caso = db.get(CasoEscalamiento, caso_id)
    if caso is None:
        raise CasoError("no_encontrado", "Caso no encontrado.")
    if caso.estado == EstadoCaso.CERRADO:
        raise CasoError("ya_cerrado", f"El caso #{caso.id} ya está cerrado.")
    if caso.responsable_id is not None and caso.responsable_id != usuario_id:
        raise CasoError(
            "asignado",
            f"El caso #{caso.id} ya está siendo atendido por "
            f"{_nombre_usuario(db, caso.responsable_id)}.",
        )

    pedido = db.get(Pedido, caso.pedido_id)
    if pedido is None:
        raise CasoError("sin_pedido", "El pedido del caso no existe.")
    if pedido.cliente is None or not pedido.cliente.telegram_chat_id:
        raise CasoError(
            "sin_telegram",
            "El cliente no tiene Telegram vinculado. Pídele que envíe su "
            "código de pedido junto con su DNI para vincular el chat.",
        )

    # Claim atómico a nivel de aplicación: la sesión se cierra por update.
    if caso.responsable_id is None:
        caso.responsable_id = usuario_id
    if caso.fecha_primera_accion is None:
        caso.fecha_primera_accion = datetime.utcnow()
    if caso.estado == EstadoCaso.ABIERTO:
        caso.estado = EstadoCaso.EN_PROCESO
    caso.updated_by_id = usuario_id

    com, envio = _crear_y_enviar(
        db, pedido, contenido,
        usuario_id=usuario_id, caso_id=caso.id, telegram=telegram,
    )
    db.commit()
    db.refresh(caso)
    db.refresh(com)

    logger.info(
        "caso_respuesta caso_id=%s com_id=%s usuario_id=%s enviado=%s",
        caso.id, com.id, usuario_id, envio.ok,
    )
    return caso, com, envio


def enviar_mensaje_humano(
    db: Session,
    pedido: Pedido,
    contenido: str,
    *,
    usuario_id: int,
    telegram: TelegramService | None = None,
) -> tuple[Comunicacion, TelegramSendResult]:
    """Mensaje de asesor sin caso asociado (panel web)."""
    com, envio = _crear_y_enviar(
        db, pedido, contenido,
        usuario_id=usuario_id, caso_id=None, telegram=telegram,
    )
    db.commit()
    db.refresh(com)
    return com, envio


def cerrar_caso(
    db: Session,
    caso_id: int,
    *,
    usuario_id: int,
    telegram: TelegramService | None = None,
    avisar_cliente: bool = True,
) -> tuple[CasoEscalamiento, Comunicacion | None]:
    """Cierra el caso y, si el cliente tiene Telegram, le avisa."""
    caso = db.get(CasoEscalamiento, caso_id)
    if caso is None:
        raise CasoError("no_encontrado", "Caso no encontrado.")
    if caso.estado == EstadoCaso.CERRADO:
        raise CasoError("ya_cerrado", f"El caso #{caso.id} ya está cerrado.")
    if caso.responsable_id is not None and caso.responsable_id != usuario_id:
        raise CasoError(
            "asignado",
            f"El caso #{caso.id} está siendo atendido por "
            f"{_nombre_usuario(db, caso.responsable_id)}.",
        )

    pedido = db.get(Pedido, caso.pedido_id)
    if caso.responsable_id is None:
        caso.responsable_id = usuario_id
    if caso.fecha_primera_accion is None:
        caso.fecha_primera_accion = datetime.utcnow()
    caso.estado = EstadoCaso.CERRADO
    caso.fecha_cierre = datetime.utcnow()
    caso.updated_by_id = usuario_id

    com: Comunicacion | None = None
    cliente = pedido.cliente if pedido else None
    if avisar_cliente and pedido is not None and cliente and cliente.telegram_chat_id:
        tg = telegram or TelegramService()
        texto = (
            f"✅ Tu caso #{caso.id} fue cerrado.\n"
            f"Pedido: {pedido.codigo}\n"
            "Gracias por contactarnos. Si necesitas algo más, escríbenos por aquí."
        )
        com, envio = _crear_y_enviar(
            db, pedido, texto,
            usuario_id=usuario_id, caso_id=caso.id, telegram=tg,
        )
        if not envio.ok:
            logger.warning(
                "caso_cierre_aviso_fallido caso_id=%s error=%s",
                caso.id, (envio.error or "")[:200],
            )

    db.commit()
    db.refresh(caso)
    if com is not None:
        db.refresh(com)
    logger.info("caso_cerrado caso_id=%s usuario_id=%s", caso.id, usuario_id)
    return caso, com

"""Webhooks de WhatsApp Business Cloud API.

GET  /webhooks/whatsapp → verificación de Meta (hub.challenge).
POST /webhooks/whatsapp → recepción de mensajes y status updates.

**Seguridad**:
- GET: comparación en tiempo constante del verify_token.
- POST: validación obligatoria de `X-Hub-Signature-256` (HMAC-SHA256 con App Secret).
- Body crudo (`await request.body()`) para el HMAC, nunca el JSON parseado.
- Deduplicación por `whatsapp_message_id` UNIQUE en BD.

**No requiere JWT** — Meta llama sin token; la autenticidad la da la firma.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.models import (
    AutorComunicacion,
    Canal,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    EstadoPedido,
    Pedido,
    Sentimiento,
)
from app.schemas.agent import IncomingMessage
from app.schemas.webhook import WebhookAckResponse
from app.services.agent_service import AgentService
from app.services.whatsapp_service import WhatsAppService

router = APIRouter()
logger = get_logger("webhooks")


# =====================================================================
# GET — verificación del webhook
# =====================================================================
@router.get("/whatsapp", summary="Verificación de webhook (Meta)")
def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
):
    challenge = WhatsAppService().verify_webhook_challenge(
        hub_mode, hub_verify_token, hub_challenge,
    )
    if challenge is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Verify token inválido")
    return int(challenge) if challenge.isdigit() else challenge


# =====================================================================
# POST — recepción de eventos
# =====================================================================
@router.post("/whatsapp", response_model=WebhookAckResponse, summary="Recepción de eventos")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")

    service = WhatsAppService()
    if not service.verify_signature(raw, signature):
        logger.warning("webhook_signature_invalid")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Firma inválida")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "JSON inválido")

    processed = 0
    duplicated = 0
    statuses_updated = 0

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            # ---- Mensajes entrantes ----
            for msg in value.get("messages", []):
                wamid = msg.get("id")
                if not wamid:
                    continue
                if db.scalar(select(Comunicacion.id).where(Comunicacion.whatsapp_message_id == wamid)):
                    duplicated += 1
                    continue
                try:
                    _process_inbound(db, msg, value)
                    processed += 1
                except IntegrityError:
                    db.rollback()
                    duplicated += 1
                except Exception:
                    logger.exception("inbound_processing_failed wamid=%s", wamid)
                    db.rollback()

            # ---- Status updates ----
            for st in value.get("statuses", []):
                if _apply_status(db, st):
                    statuses_updated += 1

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("webhook_final_commit_failed")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "No se pudo persistir el webhook",
        )

    logger.info(
        "webhook_processed processed=%s duplicated=%s statuses=%s",
        processed, duplicated, statuses_updated,
    )
    return WebhookAckResponse(
        processed=processed, duplicated=duplicated, statuses_updated=statuses_updated,
    )

# =====================================================================
# Procesamiento de mensajes entrantes
# =====================================================================
def _process_inbound(db: Session, msg: dict, value: dict) -> None:
    from app.services.llm_provider import TipoMensajeEntrante

    wa_from = msg.get("from", "")
    msg_type = msg.get("type")
    text = ""
    tipo_enum = TipoMensajeEntrante.TEXT

    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type in ("button", "interactive"):
        text = (
            msg.get("button", {}).get("text", "")
            or msg.get("interactive", {}).get("button_reply", {}).get("title", "")
            or msg.get("interactive", {}).get("list_reply", {}).get("title", "")
        )
    elif msg_type in ("image", "audio", "video", "document", "sticker", "location"):
        text = f"[{msg_type}]"
        tipo_enum = TipoMensajeEntrante.MULTIMEDIA
    else:
        text = f"[{msg_type}]"
        tipo_enum = TipoMensajeEntrante.UNKNOWN

    cliente = _find_cliente_by_phone(db, wa_from)
    pedido = None
    if cliente:
        pedido = db.scalar(
            select(Pedido)
            .where(
                Pedido.cliente_id == cliente.id,
                Pedido.estado_actual.not_in(
                    [EstadoPedido.CERRADO, EstadoPedido.CERRADO_CON_OBSERVACIONES,
                     EstadoPedido.CANCELADO]
                ),
            )
            .order_by(Pedido.fecha_ingreso.desc())
            .limit(1)
        )

    svc = AgentService(db)
    result = svc.handle_incoming_message(
        IncomingMessage(
            pedido_id=pedido.id if pedido else None,
            cliente_id=cliente.id if cliente else None,
            canal=Canal.WHATSAPP,
            contenido=text,
            tipo_mensaje=tipo_enum,
            whatsapp_message_id=msg.get("id"),
        )
    )

    incoming = db.get(Comunicacion, result.incoming_comunicacion_id)
    if incoming is not None:
        incoming.whatsapp_message_id = msg.get("id")
        incoming.estado_entrega = "RECEIVED"
        if msg.get("timestamp"):
            try:
                incoming.fecha = datetime.utcfromtimestamp(int(msg["timestamp"]))
            except (ValueError, TypeError):
                pass


def _find_cliente_by_phone(db: Session, wa_from: str) -> Cliente | None:
    """Normaliza el teléfono (quita +, espacios) y busca en cliente."""
    if not wa_from:
        return None
    normalized = "".join(c for c in wa_from if c.isdigit())
    return db.scalar(
        select(Cliente).where(
            Cliente.telefono_whatsapp.is_not(None),
            Cliente.telefono_whatsapp.like(f"%{normalized}"),
        )
    )


# =====================================================================
# Aplicar status updates (SENT → DELIVERED → READ, terminal FAILED)
# =====================================================================
_STATUS_RANK = {"PENDING": 0, "SENT": 1, "DELIVERED": 2, "READ": 3, "FAILED": 99}


def _apply_status(db: Session, st: dict) -> bool:
    wamid = st.get("id")
    new_status = (st.get("status") or "").upper()
    if not wamid or new_status not in _STATUS_RANK:
        return False

    com = db.scalar(select(Comunicacion).where(Comunicacion.whatsapp_message_id == wamid))
    if com is None:
        return False

    current = (com.estado_entrega or "PENDING").upper()
    # Solo avanzar; FAILED es terminal y sobrescribe
    if new_status == "FAILED":
        com.estado_entrega = "FAILED"
        errors = st.get("errors") or []
        if errors:
            com.error_envio = (
                f"{errors[0].get('code')}: {errors[0].get('title', '')}"[:500]
            )
        return True

    if _STATUS_RANK.get(new_status, -1) > _STATUS_RANK.get(current, -1):
        com.estado_entrega = new_status
        return True
    return False
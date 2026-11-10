"""Worker que despacha las comunicaciones en cola (`estado_entrega=PENDING`).

Para cada comunicación pendiente:
1. Resuelve el destinatario (WhatsApp o Email).
2. Envía por el canal correspondiente.
3. Actualiza `estado_entrega` (`SENT` / `FAILED`), `intentos_envio`,
   `proximo_intento` y `whatsapp_message_id`.
4. Si `intentos_envio >= WHATSAPP_MAX_RETRIES`, marca `FAILED` terminal y
   (si `EMAIL_ENABLED`) intenta fallback por correo.

Reintentos con backoff exponencial: `base * 2^intentos` (con jitter).
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import (
    AutorComunicacion,
    Canal,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    EstadoEntrega,
    EstadoHito,
    Pedido,
)
from app.services.email_service import EmailService
from app.services.whatsapp_service import WhatsAppService

logger = get_logger("outbox_worker")

_WHATSAPP_OK_STATES = {"PENDING", "FAILED_RETRY"}


class OutboxWorker:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.wa = WhatsAppService()
        self.email = EmailService()

    def process_batch(self, batch_size: int | None = None) -> dict[str, int]:
        size = batch_size or self.settings.OUTBOX_BATCH_SIZE
        now = datetime.utcnow()

        rows = self.db.scalars(
            select(Comunicacion)
            .where(
                Comunicacion.direccion == DireccionComunicacion.SALIENTE,
                Comunicacion.estado_entrega.in_(["PENDING", "FAILED_RETRY"]),
                (Comunicacion.proximo_intento.is_(None))
                | (Comunicacion.proximo_intento <= now),
            )
            .order_by(Comunicacion.id)
            .limit(size)
        ).all()

        counts = {"sent": 0, "retried": 0, "failed_terminal": 0, "skipped": 0, "email_fallback": 0}
        for com in rows:
            try:
                outcome = self._process_one(com)
                counts[outcome] += 1
            except Exception:
                logger.exception("outbox_process_failed com_id=%s", com.id)
                counts["skipped"] += 1
        self.db.commit()
        logger.info("outbox_batch_done counts=%s", counts)
        return counts

    # ---------- Lógica por comunicación ----------
    def _process_one(self, com: Comunicacion) -> str:
        pedido = self.db.get(Pedido, com.pedido_id) if com.pedido_id else None
        if pedido is None:
            self._mark_terminal_failure(com, "pedido inexistente")
            return "failed_terminal"

        cliente: Cliente = pedido.cliente

        # Canal Email directo
        if com.canal == Canal.EMAIL:
            return self._send_email(com, cliente, fallback=False)

        # WhatsApp
        if not cliente.telefono_whatsapp:
            if self.settings.EMAIL_ENABLED and cliente.email:
                return self._send_email(com, cliente, fallback=True)
            self._mark_terminal_failure(com, "cliente sin teléfono ni email")
            return "failed_terminal"

        result = self._dispatch_whatsapp(com)

        if result.ok:
            com.estado_entrega = "SENT"
            com.whatsapp_message_id = result.wamid
            com.enviado_en = datetime.utcnow()
            com.intentos_envio += 1
            com.error_envio = None
            com.proximo_intento = None
            logger.info("outbox_sent com_id=%s wamid=%s", com.id, result.wamid)
            return "sent"

        # Error no reintentable
        if not result.retriable:
            self._mark_terminal_failure(com, f"{result.error_code}: {result.error_message}")
            if self.settings.EMAIL_ENABLED and cliente.email:
                self._send_email(com, cliente, fallback=True)
                return "email_fallback"
            return "failed_terminal"

        # Reintentable → backoff
        com.intentos_envio += 1
        com.error_envio = f"{result.error_code}: {result.error_message}"[:500]
        if com.intentos_envio >= self.settings.WHATSAPP_MAX_RETRIES:
            self._mark_terminal_failure(com, "máximo de reintentos alcanzado")
            if self.settings.EMAIL_ENABLED and cliente.email:
                self._send_email(com, cliente, fallback=True)
                return "email_fallback"
            return "failed_terminal"

        com.estado_entrega = "FAILED_RETRY"
        com.proximo_intento = datetime.utcnow() + timedelta(
            seconds=self._backoff(com.intentos_envio)
        )
        logger.warning(
            "outbox_retry com_id=%s intentos=%s proximo=%s",
            com.id, com.intentos_envio, com.proximo_intento,
        )
        return "retried"

    # ---------- Helpers ----------
    def _dispatch_whatsapp(self, com: Comunicacion):
        # Si tiene plantilla whatsapp aprobada, usar send_template
        plantilla = com.plantilla
        if plantilla and plantilla.whatsapp_template_id:
            return self.wa.send_template(
                to=com.pedido.cliente.telefono_whatsapp,
                template_name=plantilla.whatsapp_template_id,
                language_code=plantilla.idioma or "es_PE",
                body_params=self._extract_body_params(com),
            )
        # Si no hay plantilla aprobada, usar texto libre (solo válido 24h)
        return self.wa.send_text(
            to=com.pedido.cliente.telefono_whatsapp,
            body=com.contenido,
        )

    def _send_email(self, com: Comunicacion, cliente: Cliente, *, fallback: bool) -> str:
        if not cliente.email:
            self._mark_terminal_failure(com, "cliente sin email")
            return "failed_terminal"
        subject = "Polux Import · Actualización de tu pedido"
        result = self.email.send(to=cliente.email, subject=subject, body=com.contenido)
        if result.ok:
            com.estado_entrega = "SENT_EMAIL"
            com.enviado_en = datetime.utcnow()
            com.error_envio = None
            com.proximo_intento = None
            logger.info("outbox_email_sent com_id=%s fallback=%s", com.id, fallback)
            return "email_fallback" if fallback else "sent"
        self._mark_terminal_failure(com, f"email: {result.error}")
        return "failed_terminal"

    def _mark_terminal_failure(self, com: Comunicacion, reason: str) -> None:
        com.estado_entrega = "FAILED"
        com.error_envio = reason[:500]
        com.proximo_intento = None
        logger.warning("outbox_terminal com_id=%s reason=%s", com.id, reason)

    def _backoff(self, attempt: int) -> int:
        base = self.settings.WHATSAPP_BACKOFF_BASE_SECONDS
        return int(base * (2 ** (attempt - 1))) + random.randint(0, 15)

    @staticmethod
    def _extract_body_params(com: Comunicacion) -> list[str]:
        """Si la plantilla espera variables, se rellenan con datos del pedido.

        En Fase 3 las plantillas usan `{{cliente_nombre}}` etc. y el cuerpo ya
        está renderizado en `com.contenido`. Para envío por WhatsApp Meta se
        necesitan parámetros estructurados; este método extrae los valores
        mínimos desde el pedido. En una iteración posterior, se guardarán los
        parámetros estructurados en la propia comunicación.
        """
        pedido = com.pedido
        if pedido is None:
            return []
        cliente = pedido.cliente
        return [cliente.nombre or "", pedido.codigo or ""]
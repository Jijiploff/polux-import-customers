"""Notificaciones consolidadas por pedido, con verificación de consentimiento."""
from __future__ import annotations

from datetime import datetime
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import (
    AutorComunicacion,
    Canal,
    ClaseComunicacion,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    Pedido,
    PlantillaMensaje,
)
from app.services.template_renderer import TemplateRenderer

logger = get_logger("notification_service")


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    # --------- API pública ---------
    def send_from_template(
        self,
        *,
        codigo_plantilla: str,
        pedido: Pedido,
        variables: Mapping[str, object],
        usuario_id: int | None = None,
    ) -> Comunicacion | None:
        """Encola un mensaje saliente usando plantilla. Guard de consentimiento."""
        plantilla = self.db.scalar(
            select(PlantillaMensaje).where(
                PlantillaMensaje.codigo == codigo_plantilla,
                PlantillaMensaje.activo== True,
            )
        )
        if plantilla is None:
            logger.warning("plantilla_inexistente codigo=%s", codigo_plantilla)
            return None

        if not self._consentimiento_vigente(pedido.cliente):
            logger.info(
                "consentimiento_revocado pedido_id=%s cliente_id=%s",
                pedido.id,
                pedido.cliente_id,
            )
            return None

        cuerpo = TemplateRenderer.render(plantilla.cuerpo, variables)
        # Telegram es el canal primario cuando el cliente ya vinculó su chat.
        canal = (
            Canal.TELEGRAM
            if pedido.cliente and pedido.cliente.telegram_chat_id
            else plantilla.canal
        )
        com = Comunicacion(
            pedido_id=pedido.id,
            direccion=DireccionComunicacion.SALIENTE,
            canal=canal,
            contenido=cuerpo,
            autor=AutorComunicacion.AGENTE,
            clase=ClaseComunicacion.CLIENTE,
            plantilla_id=plantilla.id,
            estado_entrega="PENDING",
            escalado=False,
            fecha=datetime.utcnow(),
            created_by_id=usuario_id,
            updated_by_id=usuario_id,
        )
        self.db.add(com)
        self.db.flush()
        logger.info(
            "comunicacion_encolada pedido_id=%s plantilla=%s comunicacion_id=%s",
            pedido.id,
            codigo_plantilla,
            com.id,
        )
        return com

    def send_raw_from_agent(
        self,
        *,
        pedido: Pedido,
        contenido: str,
        canal: Canal | None = None,
        intencion: str | None = None,
        sentimiento: str | None = None,
        escalado: bool = False,
        caso_id: int | None = None,
        require_consent: bool = False,
        usuario_id: int | None = None,
    ) -> Comunicacion | None:
        """Registra una respuesta reactiva del agente (texto compuesto)."""
        if require_consent and not self._consentimiento_vigente(pedido.cliente):
            logger.info("consentimiento_revocado pedido_id=%s", pedido.id)
            return None

        com = Comunicacion(
            pedido_id=pedido.id,
            direccion=DireccionComunicacion.SALIENTE,
            canal=(
                canal
                or (
                    Canal.TELEGRAM
                    if pedido.cliente and pedido.cliente.telegram_chat_id
                    else Canal.WHATSAPP
                )
            ),
            contenido=contenido,
            intencion_detectada=intencion,
            sentimiento=sentimiento,
            autor=AutorComunicacion.AGENTE,
            clase=ClaseComunicacion.CLIENTE,
            estado_entrega="PENDING",
            escalado=escalado,
            caso_id=caso_id,
            fecha=datetime.utcnow(),
            created_by_id=usuario_id,
            updated_by_id=usuario_id,
        )
        self.db.add(com)
        self.db.flush()
        logger.info(
            "comunicacion_agente pedido_id=%s intent=%s escalado=%s com_id=%s",
            pedido.id, intencion, escalado, com.id,
        )
        return com

    def send_from_plantilla_code(
        self,
        *,
        codigo_plantilla: str,
        pedido: Pedido,
        variables: Mapping[str, object],
        intencion: str | None = None,
        sentimiento: str | None = None,
        escalado: bool = False,
        caso_id: int | None = None,
        require_consent: bool = False,
        usuario_id: int | None = None,
    ) -> Comunicacion | None:
        """Variante de `send_from_template` que persiste trazabilidad del agente
        (intención, sentimiento, escalado, caso_id).
        """
        plantilla = self.db.scalar(
            select(PlantillaMensaje).where(
                PlantillaMensaje.codigo == codigo_plantilla,
                PlantillaMensaje.activo== True,
            )
        )
        if plantilla is None:
            logger.warning("plantilla_inexistente codigo=%s", codigo_plantilla)
            return None
        if require_consent and not self._consentimiento_vigente(pedido.cliente):
            logger.info("consentimiento_revocado pedido_id=%s", pedido.id)
            return None

        cuerpo = TemplateRenderer.render(plantilla.cuerpo, variables)
        canal = (
            Canal.TELEGRAM
            if pedido.cliente and pedido.cliente.telegram_chat_id
            else plantilla.canal
        )
        com = Comunicacion(
            pedido_id=pedido.id,
            direccion=DireccionComunicacion.SALIENTE,
            canal=canal,
            contenido=cuerpo,
            intencion_detectada=intencion,
            sentimiento=sentimiento,
            autor=AutorComunicacion.AGENTE,
            clase=ClaseComunicacion.CLIENTE,
            plantilla_id=plantilla.id,
            estado_entrega="PENDING",
            escalado=escalado,
            caso_id=caso_id,
            fecha=datetime.utcnow(),
            created_by_id=usuario_id,
            updated_by_id=usuario_id,
        )
        self.db.add(com)
        self.db.flush()
        logger.info(
            "comunicacion_agente_plantilla pedido_id=%s plantilla=%s com_id=%s",
            pedido.id, codigo_plantilla, com.id,
        )
        return com

    def has_plantilla_for_pedido(self, pedido_id: int, codigo_plantilla: str) -> bool:
        row = self.db.scalar(
            select(Comunicacion.id)
            .join(PlantillaMensaje, PlantillaMensaje.id == Comunicacion.plantilla_id)
            .where(
                Comunicacion.pedido_id == pedido_id,
                Comunicacion.direccion == DireccionComunicacion.SALIENTE,
                PlantillaMensaje.codigo == codigo_plantilla,
            )
            .limit(1)
        )
        return row is not None

    # --------- Helpers ---------
    @staticmethod
    def _consentimiento_vigente(cliente: Cliente) -> bool:
        return bool(cliente and cliente.consentimiento_datos)
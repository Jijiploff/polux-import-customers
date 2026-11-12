"""Agente IA acotado: clasifica intención, detecta tono y redacta mensajes.

Todo lo que NO sea clasificación/redacción (estados, fechas, decisiones,
cálculo de KPIs) proviene de la BD o del motor de reglas. Ver §7 del plan.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import (
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    ClaseComunicacion,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    EstadoCaso,
    EstadoHito,
    EstadoImprevisto,
    EstadoPedido,
    Imprevisto,
    ItemHito,
    MotivoEscalamiento,
    Pedido,
    PedidoItem,
    PrioridadCaso,
    Sentimiento,
    Entrega,
)
from app.schemas.agent import AgentResult, ClassificationRead, IncomingMessage
from app.services.llm_provider import (
    ClassificationResult,
    Intent,
    LLMProvider,
    MockProvider,
    Sentiment,
    TipoMensajeEntrante,
    contains_pii,
    extract_dates,
    get_llm_provider,
)
from app.services.notification_service import NotificationService
from app.services.knowledge_base import contexto, respuesta
from app.services.rule_engine import RuleEngine

logger = get_logger("agent_service")
settings = get_settings()

_ESTADOS_PEDIDO_LABEL = {
    EstadoPedido.RECIBIDO: "recibido",
    EstadoPedido.EN_PROCESO: "en proceso",
    EstadoPedido.LISTO_PARA_ENTREGA: "listo para entrega",
    EstadoPedido.EN_COORDINACION: "en coordinación de entrega",
    EstadoPedido.ENTREGADO: "entregado",
    EstadoPedido.CERRADO: "cerrado",
    EstadoPedido.CERRADO_CON_OBSERVACIONES: "cerrado con observaciones",
    EstadoPedido.CANCELADO: "cancelado",
}

# Intenciones que se responden con plantilla aprobada (texto cerrado).
_INTENT_TO_PLANTILLA: dict[Intent, str] = {
    Intent.SALUDO: "AGENTE_SALUDO",
    Intent.PAGOS: "AGENTE_PAGOS_REDIRECT",
}


class AgentService:
    def __init__(self, db: Session, provider: LLMProvider | None = None):
        self.db = db
        self.provider = provider or get_llm_provider()
        self.notifier = NotificationService(db)
        self.rule_engine = RuleEngine(db)
        self.settings = settings

    # =================================================================
    # Entrada
    # =================================================================
    def handle_incoming_message(self, payload: IncomingMessage) -> AgentResult:
        pedido = self._resolve_pedido(payload)
        cliente = pedido.cliente if pedido else self._resolve_cliente(payload)

        incoming = self._persist_incoming(payload, pedido)

        # Multimedia: no procesable por el LLM
        if payload.tipo_mensaje != TipoMensajeEntrante.TEXT:
            return self._handle_multimedia(pedido, incoming)

        # Anti doble-respuesta: si un humano respondió hace < N min, no responder
        if pedido is not None and self._human_in_progress(pedido.id):
            logger.info(
                "agent_skips_human_in_progress pedido_id=%s com_id=%s",
                pedido.id, incoming.id,
            )
            self.db.commit()
            return AgentResult(
                incoming_comunicacion_id=incoming.id,
                classification=ClassificationRead(
                    intent="—", sentiment="—", confidence=0.0, provider_used="skipped",
                ),
                human_in_progress=True,
                fecha_procesamiento=datetime.utcnow(),
            )

        classification, fallback = self._safe_classify(payload.contenido, pedido)
        incoming.intencion_detectada = classification.intent.value
        incoming.sentimiento = self._map_sentiment(classification.sentiment)
        self.db.flush()

        if pedido is not None and self._is_delivery_query(payload.contenido):
            return self._handle_delivery_query(
                pedido, incoming, classification, fallback,
            )

        result = self._route(
            payload=payload, pedido=pedido, cliente=cliente, incoming=incoming,
            classification=classification, fallback=fallback,
        )
        self.db.commit()
        return result

    # =================================================================
    # Resolución / persistencia
    # =================================================================
    def _resolve_pedido(self, payload: IncomingMessage) -> Pedido | None:
        if payload.pedido_id:
            return self.db.get(Pedido, payload.pedido_id)
        if payload.cliente_id:
            return self.db.scalar(
                select(Pedido)
                .where(
                    Pedido.cliente_id == payload.cliente_id,
                    Pedido.estado_actual.not_in(
                        [EstadoPedido.CERRADO, EstadoPedido.CERRADO_CON_OBSERVACIONES,
                         EstadoPedido.CANCELADO]
                    ),
                )
                .order_by(Pedido.fecha_ingreso.desc())
                .limit(1)
            )
        return None

    def _resolve_cliente(self, payload: IncomingMessage) -> Cliente | None:
        if payload.cliente_id:
            return self.db.get(Cliente, payload.cliente_id)
        return None

    def _persist_incoming(
        self, payload: IncomingMessage, pedido: Pedido | None
    ) -> Comunicacion:
        com = Comunicacion(
            pedido_id=pedido.id if pedido else None,
            direccion=DireccionComunicacion.ENTRANTE,
            canal=payload.canal,
            contenido=payload.contenido,
            autor=AutorComunicacion.CLIENTE,
            clase=ClaseComunicacion.CLIENTE,
            escalado=False,
            whatsapp_message_id=payload.whatsapp_message_id,
            fecha=datetime.utcnow(),
        )
        self.db.add(com)
        self.db.flush()
        return com

    # =================================================================
    # Clasificación con contexto y fallback
    # =================================================================
    def _safe_classify(
        self, text: str, pedido: Pedido | None
    ) -> tuple[ClassificationResult, bool]:
        context = self._conversation_context(pedido.id) if pedido else None
        try:
            return self.provider.classify(text, context=context), False
        except Exception as exc:
            logger.exception("llm_classify_failed err=%s", exc)
            result = MockProvider().classify(text)
            result.provider_used = "mock_fallback"
            return result, True

    def _conversation_context(self, pedido_id: int) -> dict[str, Any] | None:
        n = self.settings.AGENT_CONTEXT_MESSAGES
        if n <= 0:
            return None
        rows = self.db.scalars(
            select(Comunicacion)
            .where(Comunicacion.pedido_id == pedido_id)
            .order_by(Comunicacion.fecha.desc())
            .limit(n)
        ).all()
        if not rows:
            return None
        rows.reverse()
        return {
            "historial": [
                {"direccion": r.direccion.value, "autor": r.autor.value,
                 "texto": r.contenido[:240], "fecha": r.fecha.isoformat()}
                for r in rows
            ]
        }

    # =================================================================
    # Router principal
    # =================================================================
    def _route(
        self,
        *,
        payload: IncomingMessage,
        pedido: Pedido | None,
        cliente: Cliente | None,
        incoming: Comunicacion,
        classification: ClassificationResult,
        fallback: bool,
    ) -> AgentResult:
        intent = classification.intent
        sentiment = classification.sentiment
        confidence = classification.confidence

        # 1. Baja confianza → escalar (una clasificación dudosa no debe actuar sola)
        if confidence < self.settings.AGENT_MIN_CONFIDENCE:
            return self._escalate(
                pedido=pedido, cliente=cliente, incoming=incoming,
                classification=classification,
                motivo=MotivoEscalamiento.OTRO,
                prioridad=PrioridadCaso.MEDIA,
                descripcion=f"Baja confianza ({confidence:.2f}) en clasificación; requiere revisión humana.",
                fallback=fallback,
            )

        # 2. Reclamo / tono negativo / daño / producto incorrecto → SIEMPRE escalar
        if intent in (Intent.RECLAMO, Intent.DAÑO, Intent.PRODUCTO_INCORRECTO) \
                or sentiment == Sentiment.NEGATIVO:
            prioridad = (
                PrioridadCaso.CRITICA
                if intent in (Intent.DAÑO, Intent.PRODUCTO_INCORRECTO)
                else PrioridadCaso.ALTA
            )
            motivo = MotivoEscalamiento.RECLAMO
            return self._escalate(
                pedido=pedido, cliente=cliente, incoming=incoming,
                classification=classification, motivo=motivo, prioridad=prioridad,
                descripcion=f"Agente detectó {intent.value}. Escalar sin resolver.",
                fallback=fallback,
            )

        # 3. Entrega parcial → escalar (el agente NUNCA decide)
        if intent == Intent.ENTREGA_PARCIAL:
            if pedido is not None:
                caso = self.rule_engine.handle_partial_delivery_request(
                    pedido_id=pedido.id, comunicacion_id=incoming.id,
                )
                incoming.escalado = True
                incoming.caso_id = caso.id
                if self.provider.name == "mock":
                    outgoing = self.notifier.send_from_plantilla_code(
                        codigo_plantilla="AGENTE_HOLDING_ESCALAMIENTO",
                        pedido=pedido,
                        variables={"cliente_nombre": pedido.cliente.nombre},
                        intencion=intent.value,
                        sentimiento=sentiment.value,
                        escalado=True, caso_id=caso.id,
                    )
                else:
                    response_text = self._compose_escalation(
                        intent, {
                            **self._build_facts(pedido),
                            "user_question": incoming.contenido,
                            "next_step": "Un asesor evaluará la solicitud y te contactará.",
                        },
                    )
                    outgoing = self.notifier.send_raw_from_agent(
                        pedido=pedido, contenido=response_text,
                        intencion=intent.value, sentimiento=sentiment.value,
                        escalado=True, caso_id=caso.id,
                    )
                return AgentResult(
                    incoming_comunicacion_id=incoming.id,
                    outgoing_comunicacion_id=outgoing.id if outgoing else None,
                    classification=self._serialize_classification(classification),
                    escalated=True, escalation_reason="ENTREGA_PARCIAL",
                    caso_id=caso.id,
                    response_text=outgoing.contenido if outgoing else None,
                    fallback_used=fallback,
                    fecha_procesamiento=datetime.utcnow(),
                )
            # sin pedido, pedir el código antes de decidir
            return self._respond_no_pedido_id(cliente, incoming, classification, fallback)

        # 4. Pagos → derivar al canal correcto + abrir caso (cliente debe ser atendido)
        if intent == Intent.PAGOS:
            return self._escalate(
                pedido=pedido, cliente=cliente, incoming=incoming,
                classification=classification, motivo=MotivoEscalamiento.OTRO,
                prioridad=PrioridadCaso.MEDIA,
                descripcion="Consulta sobre pagos/cuotas/contrato. Derivar a canal correspondiente.",
                fallback=fallback,
                codigo_plantilla="AGENTE_PAGOS_REDIRECT",
            )

        # 5. Sin pedido y pregunta por estado → pedir código
        if pedido is None and intent in (Intent.ESTADO_PEDIDO, Intent.RETRASO):
            return self._respond_no_pedido_id(cliente, incoming, classification, fallback)

        # 6. Estado del pedido / retraso → responder con datos reales
        if pedido is not None and intent in (Intent.ESTADO_PEDIDO, Intent.RETRASO):
            return self._handle_estado(pedido, incoming, classification, fallback)

        # El modo mock conserva las plantillas auditadas. El modo IA redacta
        # también saludos y derivaciones con el contexto real de la conversación.
        if self.provider.name == "mock" and intent in _INTENT_TO_PLANTILLA and pedido is not None:
            return self._respond_from_plantilla(
                pedido=pedido, incoming=incoming,
                classification=classification,
                codigo_plantilla=_INTENT_TO_PLANTILLA[intent],
                fallback=fallback,
            )

        # 8. Consulta general / otro → composición libre
        return self._handle_general(pedido, cliente, incoming, classification, fallback)

    # =================================================================
    # Handlers
    # =================================================================
    @staticmethod
    def _is_delivery_query(text: str) -> bool:
        normalized = text.lower()
        return any(
            term in normalized
            for term in (
                "entrega", "entregar", "llegar", "llegará", "hora",
                "horario", "franja", "dirección", "direccion", "domicilio",
                "receptor", "por la tarde", "por la mañana",
            )
        )

    def _handle_delivery_query(
        self,
        pedido: Pedido,
        incoming: Comunicacion,
        classification: ClassificationResult,
        fallback: bool,
    ) -> AgentResult:
        facts = self._build_facts(pedido)
        delivery = facts.get("entrega")
        text = incoming.contenido.lower()
        if delivery is None:
            pendientes = [
                item for item in facts["items"]
                if item["estado"] != "LISTO_PARA_ENTREGA"
            ]
            if pendientes:
                esperando = ", ".join(item["descripcion"] for item in pendientes)
                response_text = (
                    f"Para el pedido **{pedido.codigo}**, aún no tenemos una entrega "
                    f"programada porque estamos esperando que llegue: {esperando}. "
                    f"La fecha prometida es el {facts['fecha_prometida']}. "
                    "¿Prefieres que coordinemos el envío cuando llegue todo?"
                )
            else:
                response_text = (
                    f"Tu pedido **{pedido.codigo}** aún no tiene una entrega programada. "
                    "Cuando esté lista podremos coordinar la fecha y el horario."
                )
        elif any(term in text for term in ("por la tarde", "por la mañana", "prefiero")):
            response_text = (
                f"Perfecto, mantendremos tu horario de {delivery['franja_horaria']}. "
                "Si deseas cambiar la dirección o la hora, dímelo y escalaré tu caso "
                "con un asesor para que lo modifique en el sistema."
            )
        else:
            address = delivery["direccion"] or "la dirección registrada"
            recipient = delivery["receptor_nombre"] or pedido.cliente.nombre
            dni = delivery["receptor_dni"] or pedido.cliente.documento
            recipient_data = f"{recipient}"
            if dni:
                recipient_data += f" (DNI {dni})"
            schedule = delivery["fecha_programada"]
            if delivery["franja_horaria"]:
                schedule += f", entre las {delivery['franja_horaria']} hrs"
            response_text = (
                f"Tu entrega está programada para el **{schedule}**. "
                f"Se enviará a: **{address}**. "
                f"El receptor es **{recipient_data}**. "
                "¿Necesitas cambiar algún detalle?"
            )
        outgoing = self.notifier.send_raw_from_agent(
            pedido=pedido,
            contenido=response_text,
            intencion=classification.intent.value,
            sentimiento=classification.sentiment.value,
            require_consent=False,
        )
        return AgentResult(
            incoming_comunicacion_id=incoming.id,
            outgoing_comunicacion_id=outgoing.id if outgoing else None,
            classification=self._serialize_classification(classification),
            escalated=False,
            response_text=response_text,
            fallback_used=fallback,
            fecha_procesamiento=datetime.utcnow(),
        )

    def _escalate(
        self,
        *,
        pedido: Pedido | None,
        cliente: Cliente | None,
        incoming: Comunicacion,
        classification: ClassificationResult,
        motivo: MotivoEscalamiento,
        prioridad: PrioridadCaso,
        descripcion: str,
        fallback: bool,
        codigo_plantilla: str = "AGENTE_HOLDING_ESCALAMIENTO",
    ) -> AgentResult:
        """Crea caso (si hay pedido) o deja el registro entrante marcado; responde holding."""
        caso_id: int | None = None
        if pedido is not None:
            # Evitar duplicado: si ya hay caso abierto para el mismo motivo → reutilizar
            caso = self.db.scalar(
                select(CasoEscalamiento).where(
                    CasoEscalamiento.pedido_id == pedido.id,
                    CasoEscalamiento.motivo == motivo,
                    CasoEscalamiento.estado.in_(
                        [EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]
                    ),
                )
            )
            if caso is None:
                caso = CasoEscalamiento(
                    pedido_id=pedido.id,
                    comunicacion_origen_id=incoming.id,
                    motivo=motivo,
                    prioridad=prioridad,
                    descripcion=descripcion,
                    fecha_apertura=datetime.utcnow(),
                    estado=EstadoCaso.ABIERTO,
                )
                self.db.add(caso)
                self.db.flush()
            caso_id = caso.id

        incoming.escalado = True
        incoming.caso_id = caso_id
        self.db.flush()

        outgoing = None
        outgoing_id: int | None = None
        response_text: str | None = None
        if pedido is not None:
            if self.provider.name == "mock":
                outgoing = self.notifier.send_from_plantilla_code(
                    codigo_plantilla=codigo_plantilla,
                    pedido=pedido,
                    variables={"cliente_nombre": pedido.cliente.nombre},
                    intencion=classification.intent.value,
                    sentimiento=classification.sentiment.value,
                    escalado=True,
                    caso_id=caso_id,
                )
            else:
                response_text = self._compose_escalation(
                    classification.intent,
                    {
                        **self._build_facts(pedido),
                        "user_question": incoming.contenido,
                        "escalated": True,
                        "priority": prioridad.value,
                        "next_step": "Un asesor revisará tu caso y te contactará.",
                    },
                )
                outgoing = self.notifier.send_raw_from_agent(
                    pedido=pedido, contenido=response_text,
                    intencion=classification.intent.value,
                    sentimiento=classification.sentiment.value,
                    escalado=True, caso_id=caso_id,
                )
            response_text = outgoing.contenido if outgoing else None
        else:
            response_text = self._compose_escalation(
                classification.intent,
                {
                    "cliente_nombre": self._first_name(cliente.nombre) if cliente else "",
                    "prioridad": prioridad.value,
                    "next_step": "Un asesor revisará tu consulta y te contactará.",
                    "user_question": incoming.contenido,
                },
            )
            outgoing = self._persist_agent_response(
                incoming, response_text, classification,
                escalated=True, caso_id=caso_id,
            )
            outgoing_id = outgoing.id

        logger.info(
            "agent_escalated pedido_id=%s motivo=%s caso_id=%s intent=%s",
            pedido.id if pedido else None, motivo.value, caso_id,
            classification.intent.value,
        )
        return AgentResult(
            incoming_comunicacion_id=incoming.id,
            outgoing_comunicacion_id=outgoing.id if outgoing else outgoing_id,
            classification=self._serialize_classification(classification),
            escalated=True,
            escalation_reason=classification.intent.value,
            caso_id=caso_id,
            response_text=response_text,
            fallback_used=fallback,
            fecha_procesamiento=datetime.utcnow(),
        )

    def _handle_estado(
        self,
        pedido: Pedido,
        incoming: Comunicacion,
        classification: ClassificationResult,
        fallback: bool,
    ) -> AgentResult:
        facts = self._build_facts(pedido)
        facts["user_question"] = incoming.contenido
        response_text, used_fallback = self._compose_with_guardrails(
            classification.intent, facts, pedido,
        )
        outgoing = self.notifier.send_raw_from_agent(
            pedido=pedido,
            contenido=response_text,
            intencion=classification.intent.value,
            sentimiento=classification.sentiment.value,
            require_consent=False,
        )
        return AgentResult(
            incoming_comunicacion_id=incoming.id,
            outgoing_comunicacion_id=outgoing.id if outgoing else None,
            classification=self._serialize_classification(classification),
            escalated=False,
            response_text=response_text,
            fallback_used=fallback or used_fallback,
            fecha_procesamiento=datetime.utcnow(),
        )

    def _respond_from_plantilla(
        self,
        *,
        pedido: Pedido,
        incoming: Comunicacion,
        classification: ClassificationResult,
        codigo_plantilla: str,
        fallback: bool,
    ) -> AgentResult:
        outgoing = self.notifier.send_from_plantilla_code(
            codigo_plantilla=codigo_plantilla,
            pedido=pedido,
            variables={"cliente_nombre": pedido.cliente.nombre},
            intencion=classification.intent.value,
            sentimiento=classification.sentiment.value,
            escalado=False,
        )
        if outgoing is None:
            # La plantilla no existe o consentimiento revocado → fallback Mock
            return self._handle_general(pedido, pedido.cliente, incoming, classification, fallback)
        return AgentResult(
            incoming_comunicacion_id=incoming.id,
            outgoing_comunicacion_id=outgoing.id,
            classification=self._serialize_classification(classification),
            escalated=False,
            response_text=outgoing.contenido,
            fallback_used=fallback,
            fecha_procesamiento=datetime.utcnow(),
        )

    def _handle_general(
        self,
        pedido: Pedido | None,
        cliente: Cliente | None,
        incoming: Comunicacion,
        classification: ClassificationResult,
        fallback: bool,
    ) -> AgentResult:
        facts = {
            "cliente_nombre": self._first_name(
                pedido.cliente.nombre if pedido else (cliente.nombre if cliente else "")
            ),
            "valid_dates": [],
            "knowledge_context": contexto() if self.provider.name == "mock" else "",
            "knowledge_answer": (
                respuesta(incoming.contenido) if self.provider.name == "mock" else None
            ),
            "sin_pedido": pedido is None,
            "user_question": incoming.contenido,
        }
        response_text, used_fallback = self._compose_with_guardrails(
            classification.intent, facts, pedido,
        )
        outgoing_id = None
        if pedido is not None:
            outgoing = self.notifier.send_raw_from_agent(
                pedido=pedido,
                contenido=response_text,
                intencion=classification.intent.value,
                sentimiento=classification.sentiment.value,
                require_consent=False,
            )
            outgoing_id = outgoing.id if outgoing else None
        else:
            outgoing = self._persist_agent_response(
                incoming, response_text, classification,
            )
            outgoing_id = outgoing.id
        return AgentResult(
            incoming_comunicacion_id=incoming.id,
            outgoing_comunicacion_id=outgoing_id,
            classification=self._serialize_classification(classification),
            escalated=False,
            response_text=response_text,
            fallback_used=fallback or used_fallback,
            fecha_procesamiento=datetime.utcnow(),
        )

    def _respond_no_pedido_id(
        self,
        cliente: Cliente | None,
        incoming: Comunicacion,
        classification: ClassificationResult,
        fallback: bool,
    ) -> AgentResult:
        nombre = self._first_name(cliente.nombre) if cliente else ""
        text = (
            f"Hola {nombre}, para consultar el estado de tu pedido necesito que "
            "me indiques tu código de pedido (por ejemplo PD-2025-0001)."
        ).strip()
        outgoing = self._persist_agent_response(incoming, text, classification)
        return AgentResult(
            incoming_comunicacion_id=incoming.id,
            outgoing_comunicacion_id=outgoing.id,
            classification=self._serialize_classification(classification),
            response_text=text,
            fallback_used=fallback,
            fecha_procesamiento=datetime.utcnow(),
        )

    def _handle_multimedia(
        self, pedido: Pedido | None, incoming: Comunicacion
    ) -> AgentResult:
        classification = ClassificationRead(
            intent="MULTIMEDIA", sentiment="NEUTRO",
            confidence=1.0, provider_used="system",
        )
        text = (
            "Hemos recibido tu mensaje. Para revisar imágenes o archivos, "
            "un asesor te contactará en breve."
        )
        outgoing_id = None
        if pedido is not None:
            caso = CasoEscalamiento(
                pedido_id=pedido.id,
                comunicacion_origen_id=incoming.id,
                motivo=MotivoEscalamiento.OTRO,
                prioridad=PrioridadCaso.MEDIA,
                descripcion="Mensaje multimedia entrante requiere revisión humana.",
                fecha_apertura=datetime.utcnow(),
                estado=EstadoCaso.ABIERTO,
            )
            self.db.add(caso)
            self.db.flush()
            incoming.escalado = True
            incoming.caso_id = caso.id
            outgoing = self.notifier.send_from_plantilla_code(
                codigo_plantilla="AGENTE_HOLDING_ESCALAMIENTO",
                pedido=pedido,
                variables={"cliente_nombre": pedido.cliente.nombre},
                intencion="MULTIMEDIA", sentimiento="NEUTRO",
                escalado=True, caso_id=caso.id,
            )
            outgoing_id = outgoing.id if outgoing else None
        self.db.commit()
        return AgentResult(
            incoming_comunicacion_id=incoming.id,
            outgoing_comunicacion_id=outgoing_id,
            classification=classification,
            escalated=pedido is not None,
            escalation_reason="MULTIMEDIA" if pedido else None,
            caso_id=incoming.caso_id,
            response_text=text,
            fecha_procesamiento=datetime.utcnow(),
        )

    # =================================================================
    # Facts (siempre desde BD)
    # =================================================================
    def _build_facts(self, pedido: Pedido) -> dict[str, Any]:
        items = self.db.scalars(
            select(PedidoItem).where(PedidoItem.pedido_id == pedido.id)
        ).all()

        items_facts: list[dict[str, Any]] = []
        valid_dates: set[str] = {pedido.fecha_prometida.strftime("%d/%m/%Y")}
        retraso_critico = False
        for item in items:
            hitos = self.db.scalars(
                select(ItemHito)
                .where(ItemHito.pedido_item_id == item.id)
                .order_by(ItemHito.id)
            ).all()
            proximo = next((h for h in hitos if h.estado.value != "COMPLETADO"), None)
            proximo_nombre = proximo.hito.nombre if proximo and proximo.hito else "—"
            fecha_prox = (
                proximo.fecha_prevista.strftime("%d/%m/%Y")
                if proximo and proximo.fecha_prevista else None
            )
            if fecha_prox:
                valid_dates.add(fecha_prox)
            if any(
                h.estado == EstadoHito.ATRASADO and h.dias_atraso > 5
                for h in hitos
            ):
                retraso_critico = True
            items_facts.append({
                "descripcion": item.descripcion_producto,
                "origen": item.origen.value,
                "estado": item.estado.value,
                "proximo_hito": proximo_nombre,
                "fecha_prevista_proximo": fecha_prox,
            })

        imprevisto_activo = self.db.scalar(
            select(Imprevisto.id).where(
                Imprevisto.pedido_id == pedido.id,
                Imprevisto.estado.in_(
                    [EstadoImprevisto.ABIERTO, EstadoImprevisto.EN_PROCESO]
                ),
            )
        ) is not None
        entrega = self.db.scalar(
            select(Entrega)
            .where(Entrega.pedido_id == pedido.id)
            .order_by(Entrega.id.desc())
        )
        entrega_facts = None
        if entrega is not None:
            entrega_facts = {
                "estado": entrega.estado.value,
                "fecha_programada": entrega.fecha_programada.strftime("%d/%m/%Y"),
                "direccion": entrega.direccion or pedido.direccion_entrega,
                "distrito": entrega.distrito,
                "franja_horaria": entrega.franja_horaria,
                "receptor_nombre": entrega.receptor_nombre,
                "receptor_dni": entrega.receptor_dni,
                "receptor_telefono": entrega.receptor_telefono,
            }

        return {
            "cliente_nombre": self._first_name(pedido.cliente.nombre),
            "pedido_codigo": pedido.codigo,
            "estado_pedido": _ESTADOS_PEDIDO_LABEL.get(
                pedido.estado_actual, pedido.estado_actual.value
            ),
            "fecha_prometida": pedido.fecha_prometida.strftime("%d/%m/%Y"),
            "items": items_facts,
            "valid_dates": sorted(valid_dates),
            "imprevisto_activo": imprevisto_activo,
            "retraso_critico": retraso_critico,
            "entrega": entrega_facts,
        }

    # =================================================================
    # Guardrails de composición
    # =================================================================
    def _compose_with_guardrails(
        self, intent: Intent, facts: dict[str, Any], pedido: Pedido | None,
    ) -> tuple[str, bool]:
        """Compone con LLM. Si inventa fechas / filtra PII / falla → fallback Mock."""
        try:
            candidate = self.provider.compose_response(intent, facts)
        except Exception as exc:
            logger.exception("llm_compose_failed err=%s", exc)
            return self._deterministic_fallback(intent, facts), True

        allowed = set(facts.get("valid_dates", []))
        detected = extract_dates(candidate)
        invented = [d for d in detected if d not in allowed]
        if invented:
            logger.warning(
                "llm_invented_dates detected=%s allowed=%s", invented, allowed,
            )
            return self._deterministic_fallback(intent, facts), True

        if pedido is not None and contains_pii(
            candidate,
            phone=pedido.cliente.telefono_whatsapp,
            email=pedido.cliente.email,
        ):
            logger.warning("llm_pii_leak pedido_id=%s", pedido.id)
            return self._deterministic_fallback(intent, facts), True

        return candidate, False

    def _deterministic_fallback(self, intent: Intent, facts: dict[str, Any]) -> str:
        return MockProvider().compose_response(intent, facts)

    def _compose_escalation(self, intent: Intent, facts: dict[str, Any]) -> str:
        if self.provider.name == "mock":
            return (
                f"Entiendo tu consulta, {facts.get('cliente_nombre', '')}. "
                "Voy a escalarla con un asesor para que la revise y te contacte."
            ).strip()
        try:
            return self.provider.compose_response(
                intent, {**facts, "escalated": True}
            ).strip()
        except Exception as exc:
            logger.exception("llm_escalation_compose_failed err=%s", exc)
            return self._deterministic_fallback(intent, facts)

    def _persist_agent_response(
        self,
        incoming: Comunicacion,
        text: str,
        classification: ClassificationResult,
        *,
        escalated: bool = False,
        caso_id: int | None = None,
    ) -> Comunicacion:
        outgoing = Comunicacion(
            pedido_id=incoming.pedido_id,
            direccion=DireccionComunicacion.SALIENTE,
            canal=incoming.canal,
            contenido=text,
            intencion_detectada=classification.intent.value,
            sentimiento=classification.sentiment.value,
            autor=AutorComunicacion.AGENTE,
            clase=ClaseComunicacion.CLIENTE,
            estado_entrega="PENDING",
            escalado=escalated,
            caso_id=caso_id,
            fecha=datetime.utcnow(),
        )
        self.db.add(outgoing)
        self.db.flush()
        return outgoing

    @staticmethod
    def _first_name(name: str | None) -> str:
        return (name or "").strip().split(" ", 1)[0]

    # =================================================================
    # Helpers
    # =================================================================
    def _human_in_progress(self, pedido_id: int) -> bool:
        """¿Un operador respondió recientemente y sigue a cargo del caso?

        Los mensajes humanos asociados a un caso ya cerrado no pausan al
        agente: al cerrar el caso, el agente retoma la conversación. Los
        mensajes sin caso o de un caso todavía activo sí mantienen la pausa.
        """
        minutes = self.settings.AGENT_RECENT_HUMAN_RESPONSE_MINUTES
        if minutes <= 0:
            return False
        limite = datetime.utcnow() - timedelta(minutes=minutes)
        casos_activos = select(CasoEscalamiento.id).where(
            CasoEscalamiento.pedido_id == pedido_id,
            CasoEscalamiento.estado.in_(
                [EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]
            ),
        )
        row = self.db.scalar(
            select(Comunicacion.id).where(
                Comunicacion.pedido_id == pedido_id,
                Comunicacion.direccion == DireccionComunicacion.SALIENTE,
                Comunicacion.autor == AutorComunicacion.HUMANO,
                Comunicacion.fecha >= limite,
                or_(
                    Comunicacion.caso_id.is_(None),
                    Comunicacion.caso_id.in_(casos_activos),
                ),
            ).limit(1)
        )
        return row is not None

    def _map_sentiment(self, s: Sentiment) -> Sentimiento:
        return {
            Sentiment.NEUTRO: Sentimiento.NEUTRO,
            Sentiment.POSITIVO: Sentimiento.POSITIVO,
            Sentiment.NEGATIVO: Sentimiento.NEGATIVO,
        }[s]

    def _serialize_classification(self, c: ClassificationResult) -> ClassificationRead:
        return ClassificationRead(
            intent=c.intent.value,
            sentiment=c.sentiment.value,
            confidence=c.confidence,
            provider_used=c.provider_used,
            model_used=c.model_used or None,
        )
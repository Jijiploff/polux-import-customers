"""Esquemas del endpoint del agente."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import Canal
from app.services.llm_provider import TipoMensajeEntrante


class IncomingMessage(BaseModel):
    """Mensaje entrante del cliente (WhatsApp, email o web)."""

    pedido_id: Optional[int] = None
    cliente_id: Optional[int] = None
    canal: Canal = Canal.WHATSAPP
    contenido: str = Field(min_length=1, max_length=4000)
    tipo_mensaje: TipoMensajeEntrante = TipoMensajeEntrante.TEXT
    whatsapp_message_id: Optional[str] = None


class ClassificationRead(BaseModel):
    intent: str
    sentiment: str
    confidence: float
    provider_used: str


class AgentResult(BaseModel):
    incoming_comunicacion_id: int
    outgoing_comunicacion_id: Optional[int] = None
    classification: ClassificationRead
    escalated: bool = False
    escalation_reason: Optional[str] = None
    caso_id: Optional[int] = None
    response_text: Optional[str] = None
    fallback_used: bool = False
    human_in_progress: bool = False
    fecha_procesamiento: datetime


class AgentMetrics(BaseModel):
    total_entrantes: int
    total_salientes: int
    escalados: int
    no_escalados: int
    tasa_escalamiento: float
    por_intent: dict[str, int]
    por_sentimiento: dict[str, int]
    con_plantilla: int
    sin_plantilla: int
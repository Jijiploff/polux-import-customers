"""Esquemas del endpoint del agente."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models import (
    AutorComunicacion,
    Canal,
    DireccionComunicacion,
    EstadoCaso,
    MotivoEscalamiento,
    PrioridadCaso,
    Sentimiento,
)
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


# =====================================================================
# Simulador de chat WhatsApp (Fase G2)
# =====================================================================
class ThreadMessage(BaseModel):
    """Un mensaje del hilo de conversación de un pedido."""

    id: int
    direccion: DireccionComunicacion
    autor: AutorComunicacion
    canal: Canal
    contenido: str
    fecha: datetime
    intencion_detectada: Optional[str] = None
    sentimiento: Optional[Sentimiento] = None
    escalado: bool = False
    caso_id: Optional[int] = None
    caso_motivo: Optional[MotivoEscalamiento] = None
    caso_prioridad: Optional[PrioridadCaso] = None
    caso_estado: Optional[EstadoCaso] = None
    plantilla_id: Optional[int] = None
    estado_entrega: Optional[str] = None


class ChatResumen(BaseModel):
    """Fila de la lista de chats del simulador."""

    pedido_id: int
    codigo: str
    estado_pedido: str
    cliente_id: int
    cliente_nombre: str
    total_mensajes: int = 0
    ultima_fecha: Optional[datetime] = None
    ultima_preview: Optional[str] = None
    ultima_autor: Optional[AutorComunicacion] = None
    caso_abierto_id: Optional[int] = None
    caso_abierto_motivo: Optional[MotivoEscalamiento] = None
    # True si un asesor respondió recientemente → el agente no interviene
    asesor_reciente: bool = False


class HumanReply(BaseModel):
    """Respuesta escrita por una persona desde la plataforma."""

    pedido_id: int
    contenido: str = Field(min_length=1, max_length=4000)


class HumanReplyResult(BaseModel):
    message: ThreadMessage
    caso_id: Optional[int] = None
    caso_estado: Optional[EstadoCaso] = None
    aviso: Optional[str] = None
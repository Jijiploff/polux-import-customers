"""Esquemas de la línea de tiempo de un pedido (Fase H).

La línea de tiempo fusiona las fuentes existentes del pedido (hitos,
mensajes, casos, imprevistos, entregas, alertas) en una sola lista
ordenada por fecha, pensada para que el operador vea la historia antes
de responder.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Tipos de evento que acepta el filtro `tipos` del endpoint.
TIPOS_EVENTO = (
    "pedido",
    "hito",
    "mensaje",
    "caso",
    "imprevisto",
    "entrega",
    "alerta",
)


class TimelineEvent(BaseModel):
    """Evento puntual de la historia del pedido."""

    fecha: datetime
    tipo: str  # uno de TIPOS_EVENTO
    titulo: str
    detalle: Optional[str] = None
    criticidad: str = "INFO"  # INFO | MEDIA | ALTA
    ref_tipo: Optional[str] = None  # tabla de origen (comunicacion, caso, ...)
    ref_id: Optional[int] = None
    autor: Optional[str] = None  # solo eventos de mensaje: CLIENTE|AGENTE|HUMANO


class TimelineResumen(BaseModel):
    """Contadores rápidos: contexto de un vistazo al responder."""

    mensajes: int = 0
    mensajes_clave: int = 0
    hitos_atrasados: int = 0
    casos_abiertos: int = 0
    imprevistos_abiertos: int = 0
    alertas_activas: int = 0


class TimelineRead(BaseModel):
    """Respuesta de `GET /pedidos/{id}/timeline`."""

    pedido_id: int
    resumen: TimelineResumen
    eventos: list[TimelineEvent] = Field(default_factory=list)
    incluyendo_mensajes: bool = False

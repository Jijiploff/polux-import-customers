"""Esquemas de comunicaciones, alertas, imprevistos y casos de escalamiento."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models import (
    AutorComunicacion,
    Canal,
    DireccionComunicacion,
    EstadoAlerta,
    EstadoCaso,
    EstadoImprevisto,
    MotivoEscalamiento,
    PrioridadCaso,
    Sentimiento,
    SeveridadAlerta,
    TipoAlerta,
    TipoImprevisto,
)


class _OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ComunicacionCreate(BaseModel):
    pedido_id: Optional[int] = None
    pedido_item_id: Optional[int] = None
    direccion: DireccionComunicacion
    canal: Canal
    contenido: str
    intencion_detectada: Optional[str] = None
    sentimiento: Optional[Sentimiento] = None
    autor: AutorComunicacion
    plantilla_id: Optional[int] = None
    escalado: bool = False
    fecha: Optional[datetime] = None


class ComunicacionRead(_OrmModel):
    id: int
    pedido_id: Optional[int]
    direccion: DireccionComunicacion
    canal: Canal
    contenido: str
    intencion_detectada: Optional[str]
    sentimiento: Optional[Sentimiento]
    autor: AutorComunicacion
    escalado: bool
    fecha: datetime


class AlertaRead(_OrmModel):
    id: int
    tipo: TipoAlerta
    pedido_id: int
    severidad: SeveridadAlerta
    mensaje: str
    estado: EstadoAlerta
    fecha_deteccion: datetime


class ImprevistoCreate(BaseModel):
    pedido_id: int
    pedido_item_id: Optional[int] = None
    tipo: TipoImprevisto
    descripcion: str
    fecha_deteccion: datetime


class ImprevistoUpdate(BaseModel):
    estado: EstadoImprevisto
    resolucion: Optional[str] = None
    fecha_resolucion: Optional[datetime] = None


class ImprevistoRead(_OrmModel):
    id: int
    pedido_id: int
    pedido_item_id: Optional[int]
    tipo: TipoImprevisto
    descripcion: str
    fecha_deteccion: datetime
    fecha_resolucion: Optional[datetime]
    estado: EstadoImprevisto
    resolucion: Optional[str]


class CasoRead(_OrmModel):
    id: int
    pedido_id: int
    motivo: MotivoEscalamiento
    prioridad: PrioridadCaso
    descripcion: str
    fecha_apertura: datetime
    fecha_primera_accion: Optional[datetime]
    responsable_id: Optional[int]
    estado: EstadoCaso
    fecha_cierre: Optional[datetime]


class CasoCreate(BaseModel):
    pedido_id: int
    motivo: MotivoEscalamiento
    prioridad: PrioridadCaso = PrioridadCaso.MEDIA
    descripcion: str


class CasoUpdate(BaseModel):
    estado: Optional[EstadoCaso] = None
    responsable_id: Optional[int] = None
    registrar_primera_accion: bool = False

class AlertaUpdate(BaseModel):
    estado: EstadoAlerta
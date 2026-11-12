"""Esquemas de comunicaciones, alertas, imprevistos y casos de escalamiento."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    AutorComunicacion,
    Canal,
    ClaseComunicacion,
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
from app.schemas.agent import ThreadMessage


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
    clase: ClaseComunicacion = ClaseComunicacion.CLIENTE
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
    clase: ClaseComunicacion
    escalado: bool
    fecha: datetime


class AlertaRead(_OrmModel):
    id: int
    tipo: TipoAlerta
    pedido_id: int
    pedido_codigo: Optional[str] = None
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
    pedido_codigo: Optional[str] = None
    motivo: MotivoEscalamiento
    prioridad: PrioridadCaso
    descripcion: str
    fecha_apertura: datetime
    fecha_primera_accion: Optional[datetime]
    responsable_id: Optional[int]
    responsable_nombre: Optional[str] = None
    estado: EstadoCaso
    fecha_cierre: Optional[datetime]


class CasoCreate(BaseModel):
    pedido_id: int
    motivo: MotivoEscalamiento
    prioridad: PrioridadCaso = PrioridadCaso.MEDIA
    descripcion: str


class CasoUpdate(BaseModel):
    estado: Optional[EstadoCaso] = None
    responsable_id: Optional[int] = Field(
        default=None,
        description=(
            "Obsoleto. Usa POST /casos/{caso_id}/reasignar: la asignación "
            "debe quedar auditada y notificada."
        ),
    )
    registrar_primera_accion: bool = False


class CasoReasignacionCreate(BaseModel):
    """Admin asigna/reasigna; el operador sólo puede liberar su propio caso."""

    responsable_id: Optional[int] = None


class CasoReasignacionRead(BaseModel):
    caso: CasoRead
    aviso: Optional[str] = None


class CasoDetalleRead(CasoRead):
    """Ficha del caso con el contexto necesario para responderlo."""

    pedido_codigo: str
    cliente_nombre: str
    cliente_telegram_vinculado: bool = False
    puede_responder: bool = False


class CasoRespuestaCreate(BaseModel):
    contenido: str = Field(min_length=1, max_length=4000)


class CasoRespuestaRead(BaseModel):
    message: ThreadMessage
    caso_id: int
    caso_estado: EstadoCaso
    enviado: bool
    aviso: Optional[str] = None


class CasoCierreRead(BaseModel):
    caso: CasoRead
    aviso: Optional[str] = None


class AlertaUpdate(BaseModel):
    estado: EstadoAlerta
"""Esquemas de entregas y conformidad."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    EstadoEntrega,
    ModalidadEntrega,
    ResultadoConformidad,
    TipoEntrega,
)


class _OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ConformidadItemIn(BaseModel):
    pedido_item_id: int
    checklist_caja_sellada: bool = False
    checklist_modelo_ok: bool = False
    checklist_color_ok: bool = False
    checklist_capacidad_ok: bool = False
    checklist_imei_ok: bool = False
    checklist_accesorios_ok: bool = False
    resultado: ResultadoConformidad
    observaciones: Optional[str] = None
    evidencias_urls: Optional[str] = None


class EntregaItemRead(_OrmModel):
    id: int
    pedido_item_id: int


class ConformidadRead(_OrmModel):
    id: int
    entrega_item_id: int
    resultado: ResultadoConformidad
    observaciones: Optional[str]
    evidencias_urls: Optional[str]
    fecha_registro: datetime


class EntregaRead(_OrmModel):
    id: int
    pedido_id: int
    tipo: TipoEntrega
    modalidad: ModalidadEntrega
    estado: EstadoEntrega
    fecha_programada: datetime
    fecha_real: Optional[datetime]
    autorizada_por_id: Optional[int]
    fecha_autorizacion: Optional[datetime]
    motivo_parcial: Optional[str]
    items: list[EntregaItemRead] = Field(default_factory=list)


class EntregaCreate(BaseModel):
    pedido_id: int
    tipo: TipoEntrega = TipoEntrega.COMPLETA
    modalidad: ModalidadEntrega
    fecha_programada: datetime
    pedido_item_ids: list[int] = Field(default_factory=list)
    autorizada_por_id: Optional[int] = None
    fecha_autorizacion: Optional[datetime] = None
    motivo_parcial: Optional[str] = None


class EntregaCompletar(BaseModel):
    fecha_real: datetime
    conformidades: list[ConformidadItemIn]
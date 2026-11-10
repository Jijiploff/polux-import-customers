"""Esquemas Pydantic v2 del dominio de pedidos e hitos."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import (
    EstadoHito,
    EstadoIngreso,
    EstadoItem,
    EstadoPedido,
    ModalidadEntrega,
    OrigenItem,
)


class _OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClienteResumen(_OrmModel):
    id: int
    nombre: str
    telefono_whatsapp: Optional[str] = None
    email: Optional[str] = None
    consentimiento_datos: bool


class ItemHitoRead(_OrmModel):
    """Se usa también anidado en `PedidoItemDetail.hitos`.

    Como `hito_codigo` / `hito_nombre` no son columnas de `ItemHito` (viven en
    `HitoCatalogo`), necesitamos un `model_validator(mode="before")` que los
    extraiga de la relación. Sin él, la serialización anidada devolvía "".
    """

    id: int
    hito_id: int
    hito_codigo: str = ""
    hito_nombre: str = ""
    fecha_prevista: Optional[datetime]
    fecha_real: Optional[datetime]
    estado: EstadoHito
    dias_atraso: int
    notificado_cliente: bool

    @model_validator(mode="before")
    @classmethod
    def _fill_hito_fields(cls, data):
        # Si ya viene como dict (por ejemplo desde hitos.py `_serialize`), respetamos.
        if isinstance(data, dict):
            return data
        hito = getattr(data, "hito", None)
        if hito is None:
            return data
        return {
            "id": data.id,
            "hito_id": data.hito_id,
            "hito_codigo": hito.codigo,
            "hito_nombre": hito.nombre,
            "fecha_prevista": data.fecha_prevista,
            "fecha_real": data.fecha_real,
            "estado": data.estado,
            "dias_atraso": data.dias_atraso,
            "notificado_cliente": data.notificado_cliente,
        }


class PedidoItemRead(_OrmModel):
    id: int
    producto_id: Optional[int]
    descripcion_producto: str
    modelo: Optional[str]
    color: Optional[str]
    capacidad: Optional[str]
    cantidad: int
    accesorios: Optional[str]
    origen: OrigenItem
    estado: EstadoItem


class PedidoRead(_OrmModel):
    id: int
    codigo: str
    cliente_id: int
    contrato_id: Optional[int]
    estado_ingreso: EstadoIngreso
    estado_actual: EstadoPedido
    fecha_ingreso: datetime
    fecha_prometida: datetime
    modalidad_entrega: ModalidadEntrega
    direccion_entrega: Optional[str]
    consentimiento_comunicaciones: bool


class PedidoDetail(PedidoRead):
    cliente: ClienteResumen
    items: list[PedidoItemRead]


class PedidoItemDetail(PedidoItemRead):
    hitos: list[ItemHitoRead] = Field(default_factory=list)


class PedidoFullDetail(PedidoRead):
    cliente: ClienteResumen
    items: list[PedidoItemDetail]


class ItemEstadoUpdate(BaseModel):
    estado: EstadoItem


class HitoCompletar(BaseModel):
    fecha_real: datetime
    observacion: Optional[str] = None


class HitoRead(_OrmModel):
    id: int
    pedido_item_id: int
    hito_id: int
    fecha_prevista: Optional[datetime]
    fecha_real: Optional[datetime]
    estado: EstadoHito
    dias_atraso: int
    notificado_cliente: bool
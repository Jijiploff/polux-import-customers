"""Pedido, ítem, hitos, SLA y seguimiento por ítem."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    Unicode,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base_mixins import AuditUserMixin, TimestampMixin


class EstadoIngreso(str, enum.Enum):
    PRIMER_PAGO_VERIFICADO = "PRIMER_PAGO_VERIFICADO"
    PAGO_COMPLETO_VERIFICADO = "PAGO_COMPLETO_VERIFICADO"


class EstadoPedido(str, enum.Enum):
    RECIBIDO = "RECIBIDO"
    EN_PROCESO = "EN_PROCESO"
    LISTO_PARA_ENTREGA = "LISTO_PARA_ENTREGA"
    EN_COORDINACION = "EN_COORDINACION"
    ENTREGADO = "ENTREGADO"
    CERRADO = "CERRADO"
    CERRADO_CON_OBSERVACIONES = "CERRADO_CON_OBSERVACIONES"
    CANCELADO = "CANCELADO"


class ModalidadEntrega(str, enum.Enum):
    DOMICILIO = "DOMICILIO"
    RECOJO = "RECOJO"


class OrigenItem(str, enum.Enum):
    STOCK_TRUJILLO = "STOCK_TRUJILLO"
    IMPORTACION = "IMPORTACION"


class EstadoItem(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    LISTO_PARA_ENTREGA = "LISTO_PARA_ENTREGA"
    ENTREGADO = "ENTREGADO"
    CON_OBSERVACIONES = "CON_OBSERVACIONES"


class EstadoHito(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    EN_PROCESO = "EN_PROCESO"
    COMPLETADO = "COMPLETADO"
    ATRASADO = "ATRASADO"
    OMITIDO = "OMITIDO"


class Pedido(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "pedido"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(60), unique=True, nullable=False)
    contrato_id: Mapped[int | None] = mapped_column(
        ForeignKey("contrato.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("cliente.id", ondelete="NO ACTION"), nullable=False, index=True
    )
    estado_ingreso: Mapped[EstadoIngreso] = mapped_column(
        SAEnum(EstadoIngreso, native_enum=False, length=40), nullable=False
    )
    estado_actual: Mapped[EstadoPedido] = mapped_column(
        SAEnum(EstadoPedido, native_enum=False, length=40),
        nullable=False,
        default=EstadoPedido.RECIBIDO,
        index=True,
    )
    fecha_ingreso: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fecha_prometida: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    modalidad_entrega: Mapped[ModalidadEntrega] = mapped_column(
        SAEnum(ModalidadEntrega, native_enum=False, length=20), nullable=False
    )
    direccion_entrega: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    consentimiento_comunicaciones: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    cliente = relationship("Cliente", back_populates="pedidos")
    contrato = relationship("Contrato", back_populates="pedidos")
    items = relationship("PedidoItem", back_populates="pedido", cascade="all, delete-orphan")
    entregas = relationship("Entrega", back_populates="pedido")


class PedidoItem(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "pedido_item"
    __table_args__ = (
        CheckConstraint("cantidad > 0", name="ck_pedido_item_cantidad_pos"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("producto.id", ondelete="SET NULL"), nullable=True, index=True
    )
    descripcion_producto: Mapped[str] = mapped_column(Unicode(300), nullable=False)
    modelo: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    color: Mapped[str | None] = mapped_column(Unicode(80), nullable=True)
    capacidad: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    accesorios: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
    origen: Mapped[OrigenItem] = mapped_column(
        SAEnum(OrigenItem, native_enum=False, length=20), nullable=False, index=True
    )
    estado: Mapped[EstadoItem] = mapped_column(
        SAEnum(EstadoItem, native_enum=False, length=30),
        nullable=False,
        default=EstadoItem.PENDIENTE,
        index=True,
    )

    pedido = relationship("Pedido", back_populates="items")
    producto = relationship("Producto")
    hitos = relationship("ItemHito", back_populates="item", cascade="all, delete-orphan")


class HitoCatalogo(Base, TimestampMixin):
    __tablename__ = "hito_catalogo"
    __table_args__ = (
        UniqueConstraint("codigo", name="uq_hito_catalogo_codigo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(60), nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    origen: Mapped[OrigenItem] = mapped_column(
        SAEnum(OrigenItem, native_enum=False, length=20), nullable=False, index=True
    )
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SlaHito(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "sla_hito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hito_id: Mapped[int] = mapped_column(
        ForeignKey("hito_catalogo.id", ondelete="CASCADE"), nullable=False, index=True
    )
    origen: Mapped[OrigenItem] = mapped_column(
        SAEnum(OrigenItem, native_enum=False, length=20), nullable=False
    )
    dias_maximos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    horas_maximas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    hito = relationship("HitoCatalogo")


class ItemHito(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "item_hito"
    __table_args__ = (
        UniqueConstraint("pedido_item_id", "hito_id", name="uq_item_hito_item_hito"),
        CheckConstraint(
            "(estado NOT IN ('COMPLETADO','OMITIDO')) OR (fecha_real IS NOT NULL)",
            name="ck_item_hito_real_required",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_item_id: Mapped[int] = mapped_column(
        ForeignKey("pedido_item.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hito_id: Mapped[int] = mapped_column(
        ForeignKey("hito_catalogo.id", ondelete="NO ACTION"), nullable=False, index=True
    )
    fecha_prevista: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    fecha_real: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    estado: Mapped[EstadoHito] = mapped_column(
        SAEnum(EstadoHito, native_enum=False, length=20),
        nullable=False,
        default=EstadoHito.PENDIENTE,
        index=True,
    )
    dias_atraso: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notificado_cliente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fecha_notificacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    item = relationship("PedidoItem", back_populates="hitos")
    hito = relationship("HitoCatalogo")
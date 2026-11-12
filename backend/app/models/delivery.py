"""Entregas, conformidad y reglas de negocio parametrizables."""
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
    Unicode,
    UnicodeText,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base_mixins import AuditUserMixin, TimestampMixin
from app.models.orders import ModalidadEntrega


class TipoEntrega(str, enum.Enum):
    COMPLETA = "COMPLETA"
    PARCIAL = "PARCIAL"


class EstadoEntrega(str, enum.Enum):
    BORRADOR = "BORRADOR"
    PROGRAMADA = "PROGRAMADA"
    EN_RUTA = "EN_RUTA"
    ENTREGADA = "ENTREGADA"
    FALLIDA = "FALLIDA"
    REPROGRAMADA = "REPROGRAMADA"
    RECHAZADA = "RECHAZADA"


class ResultadoConformidad(str, enum.Enum):
    CONFORME = "CONFORME"
    CON_OBSERVACIONES = "CON_OBSERVACIONES"


class TipoValorRegla(str, enum.Enum):
    INT = "INT"
    DECIMAL = "DECIMAL"
    STRING = "STRING"
    BOOL = "BOOL"
    JSON = "JSON"


class Entrega(Base, TimestampMixin, AuditUserMixin):
    """Entrega (completa o parcial).

    Regla inviolable: una entrega parcial exige autorización humana
    registrada (quién, cuándo, por qué). Se fuerza con CHECK a nivel BD.
    """
    __tablename__ = "entrega"
    __table_args__ = (
        CheckConstraint(
            "(tipo <> 'PARCIAL') OR "
            "(autorizada_por_id IS NOT NULL AND fecha_autorizacion IS NOT NULL AND motivo_parcial IS NOT NULL)",
            name="ck_entrega_parcial_requiere_autorizacion",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(
        ForeignKey("pedido.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo: Mapped[TipoEntrega] = mapped_column(
        SAEnum(TipoEntrega, native_enum=False, length=20), nullable=False, index=True
    )
    modalidad: Mapped[ModalidadEntrega] = mapped_column(
        SAEnum(ModalidadEntrega, native_enum=False, length=20), nullable=False
    )
    fecha_programada: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    fecha_real: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    responsable_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"), nullable=True
    )
    estado: Mapped[EstadoEntrega] = mapped_column(
        SAEnum(EstadoEntrega, native_enum=False, length=20),
        nullable=False,
        default=EstadoEntrega.PROGRAMADA,
        index=True,
    )
    autorizada_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"), nullable=True
    )
    fecha_autorizacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_parcial: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    direccion: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    distrito: Mapped[str | None] = mapped_column(Unicode(120), nullable=True)
    punto_recojo: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    referencia: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)
    receptor_nombre: Mapped[str | None] = mapped_column(Unicode(160), nullable=True)
    receptor_dni: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    receptor_telefono: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    franja_horaria: Mapped[str | None] = mapped_column(Unicode(40), nullable=True)
    notas_courier: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    creado_por_agente: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    fecha_confirmacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    receptor_verificado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recibido_por: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)

    pedido = relationship("Pedido", back_populates="entregas")
    items = relationship("EntregaItem", back_populates="entrega", cascade="all, delete-orphan")


class CoordinacionEntrega(Base, TimestampMixin):
    """Estado persistente del asistente de coordinación por Telegram."""
    __tablename__ = "coordinacion_entrega"
    __table_args__ = (UniqueConstraint("chat_id", name="uq_coordinacion_entrega_chat"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str] = mapped_column(Unicode(40), nullable=False)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedido.id"), nullable=False, index=True)
    fase: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    datos: Mapped[str] = mapped_column(UnicodeText, nullable=False, default="{}")

    pedido = relationship("Pedido")


class EntregaItem(Base, TimestampMixin):
    __tablename__ = "entrega_item"
    __table_args__ = (
        UniqueConstraint("entrega_id", "pedido_item_id", name="uq_entrega_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entrega_id: Mapped[int] = mapped_column(
        ForeignKey("entrega.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pedido_item_id: Mapped[int] = mapped_column(
        ForeignKey("pedido_item.id", ondelete="NO ACTION"), nullable=False, index=True
    )

    entrega = relationship("Entrega", back_populates="items")
    conformidad = relationship(
        "Conformidad", back_populates="entrega_item", uselist=False, cascade="all, delete-orphan"
    )


class Conformidad(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "conformidad"
    __table_args__ = (
        CheckConstraint(
            "(resultado <> 'CON_OBSERVACIONES') OR (observaciones IS NOT NULL)",
            name="ck_conformidad_obs_required",
        ),
        UniqueConstraint("entrega_item_id", name="uq_conformidad_entrega_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entrega_item_id: Mapped[int] = mapped_column(
        ForeignKey("entrega_item.id", ondelete="CASCADE"), nullable=False
    )
    checklist_caja_sellada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checklist_modelo_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checklist_color_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checklist_capacidad_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checklist_imei_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checklist_accesorios_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resultado: Mapped[ResultadoConformidad] = mapped_column(
        SAEnum(ResultadoConformidad, native_enum=False, length=20), nullable=False
    )
    observaciones: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    evidencias_urls: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    registrado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id"), nullable=True
    )

    entrega_item = relationship("EntregaItem", back_populates="conformidad")


class ReglaNegocio(Base, TimestampMixin, AuditUserMixin):
    __tablename__ = "regla_negocio"
    __table_args__ = (UniqueConstraint("codigo", name="uq_regla_codigo"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(60), nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Unicode(400), nullable=True)
    categoria: Mapped[str] = mapped_column(Unicode(40), nullable=False, index=True)
    valor: Mapped[str] = mapped_column(Unicode(400), nullable=False)
    tipo_valor: Mapped[TipoValorRegla] = mapped_column(
        SAEnum(TipoValorRegla, native_enum=False, length=10), nullable=False
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
"""Modelo dimensional: dimensiones y hechos para el dashboard de KPIs.

Las dimensiones se pueblan por seed (`dim_tiempo`, `dim_canal`,
`dim_tipo_imprevisto`, `dim_kpi`) o por sincronización desde catálogos
(`dim_producto`, `dim_hito`). Los hechos se alimentan desde el motor de
reglas (Fase 3) o mediante procesos ETL programados. En esta fase se crea
únicamente la estructura.
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    Unicode,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.base_mixins import TimestampMixin


class NivelKpi(str, enum.Enum):
    OPTIMO = "OPTIMO"
    ALERTA = "ALERTA"
    CRITICO = "CRITICO"


class DimTiempo(Base):
    __tablename__ = "dim_tiempo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # yyyymmdd
    fecha: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    mes: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dia: Mapped[int] = mapped_column(Integer, nullable=False)
    trimestre: Mapped[int] = mapped_column(Integer, nullable=False)
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre_mes: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    es_fin_semana: Mapped[bool] = mapped_column(Boolean, nullable=False)


class DimCanal(Base, TimestampMixin):
    __tablename__ = "dim_canal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(60), nullable=False)


class DimTipoImprevisto(Base, TimestampMixin):
    __tablename__ = "dim_tipo_imprevisto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(60), nullable=False)
    categoria: Mapped[str] = mapped_column(Unicode(30), nullable=False)


class DimProducto(Base, TimestampMixin):
    __tablename__ = "dim_producto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("producto.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sku: Mapped[str] = mapped_column(Unicode(60), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    categoria: Mapped[str] = mapped_column(Unicode(30), nullable=False)


class DimHito(Base, TimestampMixin):
    __tablename__ = "dim_hito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hito_id: Mapped[int | None] = mapped_column(
        ForeignKey("hito_catalogo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    codigo: Mapped[str] = mapped_column(Unicode(60), nullable=False, unique=True)
    nombre: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    origen: Mapped[str] = mapped_column(Unicode(20), nullable=False)


class DimKpi(Base, TimestampMixin):
    __tablename__ = "dim_kpi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(Unicode(60), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    definicion: Mapped[str] = mapped_column(Unicode(500), nullable=False)
    unidad: Mapped[str] = mapped_column(Unicode(20), nullable=False)  # %, horas, días
    umbral_optimo: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    umbral_alerta: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    umbral_critico: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    sentido: Mapped[str] = mapped_column(Unicode(20), nullable=False)  # "mayor_mejor"/"menor_mejor"
    es_complementario: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ---------- Hechos ----------
class FactHitoPedido(Base, TimestampMixin):
    __tablename__ = "fact_hito_pedido"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tiempo_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_tiempo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    hito_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_hito.id", ondelete="SET NULL"), nullable=True, index=True
    )
    producto_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_producto.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pedido_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pedido_item_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    item_hito_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    completado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notificado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notificado_oportuno: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dias_atraso: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    origen: Mapped[str | None] = mapped_column(Unicode(20), nullable=True, index=True)
    operador_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

class FactComunicacion(Base, TimestampMixin):
    __tablename__ = "fact_comunicacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tiempo_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_tiempo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    canal_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_canal.id", ondelete="SET NULL"), nullable=True, index=True
    )
    comunicacion_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    pedido_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    direccion: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    autor: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    escalado: Mapped[bool] = mapped_column(Boolean, nullable=False)
    sentimiento: Mapped[str | None] = mapped_column(Unicode(20), nullable=True)


class FactEscalamiento(Base, TimestampMixin):
    __tablename__ = "fact_escalamiento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tiempo_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_tiempo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    caso_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    pedido_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    motivo: Mapped[str] = mapped_column(Unicode(30), nullable=False)
    prioridad: Mapped[str] = mapped_column(Unicode(10), nullable=False)
    horas_respuesta: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)


class FactImprevisto(Base, TimestampMixin):
    __tablename__ = "fact_imprevisto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tiempo_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_tiempo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tipo_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_tipo_imprevisto.id", ondelete="SET NULL"), nullable=True, index=True
    )
    imprevisto_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    pedido_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    dias_resolucion: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)


class FactEntrega(Base, TimestampMixin):
    __tablename__ = "fact_entrega"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tiempo_id: Mapped[int | None] = mapped_column(
        ForeignKey("dim_tiempo.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entrega_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    pedido_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    a_tiempo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    con_observaciones: Mapped[bool] = mapped_column(Boolean, nullable=False)
"""Adaptadores del núcleo Polux Import (cliente, producto, contrato) + RBAC.

NOTA DE INTEGRACIÓN
-------------------
El esquema real del núcleo no fue provisto. Estas tres tablas son un
*adaptador*: mantienen la forma que la Fase Customers necesita y exponen
`core_id` (nullable) como punto de enganche al sistema existente.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.base_mixins import AuditUserMixin, TimestampMixin


class CategoriaProducto(str, enum.Enum):
    IPHONE = "IPHONE"
    MACBOOK = "MACBOOK"
    IPAD = "IPAD"
    AIRPODS = "AIRPODS"
    ACCESORIO = "ACCESORIO"
    OTRO = "OTRO"


class RolCodigo(str, enum.Enum):
    ADMIN = "ADMIN"
    OPERADOR = "OPERADOR"
    GERENTE = "GERENTE"


# ---------- RBAC ----------
class Rol(Base, TimestampMixin):
    __tablename__ = "rol"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[RolCodigo] = mapped_column(
        SAEnum(RolCodigo, native_enum=False, length=20), unique=True, nullable=False
    )
    nombre: Mapped[str] = mapped_column(Unicode(80), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Unicode(300), nullable=True)


class Usuario(Base, TimestampMixin):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Unicode(200), unique=True, nullable=False)
    nombre_completo: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(Unicode(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    roles = relationship("UsuarioRol", back_populates="usuario", cascade="all, delete-orphan")


class UsuarioRol(Base):
    __tablename__ = "usuario_rol"
    __table_args__ = (UniqueConstraint("usuario_id", "rol_id", name="uq_usuario_rol"),)

    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    rol_id: Mapped[int] = mapped_column(ForeignKey("rol.id", ondelete="CASCADE"), primary_key=True)

    usuario = relationship("Usuario", back_populates="roles")
    rol = relationship("Rol")


# ---------- Core (adaptadores) ----------
class Cliente(Base, TimestampMixin, AuditUserMixin):
    """Adaptador al maestro de clientes del core Polux Import."""

    __tablename__ = "cliente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    core_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    documento: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    nombre: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    telefono_whatsapp: Mapped[str | None] = mapped_column(Unicode(30), nullable=True)
    email: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)

    # Consentimiento (Ley 29733)
    consentimiento_datos: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consentimiento_fecha: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consentimiento_revocado_fecha: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    pedidos = relationship("Pedido", back_populates="cliente")


class Producto(Base, TimestampMixin, AuditUserMixin):
    """Adaptador al maestro de productos del core Polux Import."""

    __tablename__ = "producto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    core_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sku: Mapped[str] = mapped_column(Unicode(60), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(200), nullable=False)
    categoria: Mapped[CategoriaProducto] = mapped_column(
        SAEnum(CategoriaProducto, native_enum=False, length=20), nullable=False
    )
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Contrato(Base, TimestampMixin, AuditUserMixin):
    """Adaptador al maestro de contratos del core Polux Import."""

    __tablename__ = "contrato"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    core_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    numero: Mapped[str] = mapped_column(Unicode(60), unique=True, nullable=False)
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("cliente.id", ondelete="NO ACTION"), nullable=False, index=True
    )
    fecha_firma: Mapped[date] = mapped_column(Date, nullable=False)
    monto_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(Unicode(3), nullable=False, default="USD")

    cliente = relationship("Cliente")
    pedidos = relationship("Pedido", back_populates="contrato")
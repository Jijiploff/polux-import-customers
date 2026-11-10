"""Mixins comunes de auditoría para tablas del dominio.

Las FK a `usuario` NO llevan ON DELETE porque los usuarios del sistema
nunca se eliminan físicamente (solo se desactivan con `activo=false`).
Esto evita el error de SQL Server "multiple cascade paths" (1785).
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """`created_at` / `updated_at` gestionados por la BD (fuente de verdad)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.sysutcdatetime(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.sysutcdatetime(),
        onupdate=func.sysutcdatetime(),
        nullable=False,
    )


class AuditUserMixin:
    """Usuario que crea / modifica. FK laxa a `usuario`, sin acción de cascada."""

    created_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuario.id"), nullable=True
    )
    updated_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuario.id"), nullable=True
    )
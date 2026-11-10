"""Añade columnas de control de outbox a `comunicacion` (idempotente).

Nota: si el modelo `Comunicacion` ya incluye estas columnas (como en la
versión final del proyecto), `0001_initial_schema` las habrá creado vía
`Base.metadata.create_all`. En ese caso, esta migración no hace nada
(usa `COL_LENGTH` para detectar columnas existentes).

Revision ID: 0003_outbox_columns
Revises: 0002_kpi_views
Create Date: 2025-01-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003_outbox_columns"
down_revision: Union[str, None] = "0002_kpi_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Columnas (solo si no existen)
    stmts = [
        # intentos_envio: INT NOT NULL DEFAULT 0
        """
        IF COL_LENGTH('comunicacion', 'intentos_envio') IS NULL
        BEGIN
            ALTER TABLE comunicacion
            ADD intentos_envio INT NOT NULL
                CONSTRAINT DF_comunicacion_intentos_envio DEFAULT 0
        END
        """,
        # proximo_intento: DATETIME NULL
        """
        IF COL_LENGTH('comunicacion', 'proximo_intento') IS NULL
            ALTER TABLE comunicacion ADD proximo_intento DATETIME NULL
        """,
        # error_envio: NVARCHAR(500) NULL
        """
        IF COL_LENGTH('comunicacion', 'error_envio') IS NULL
            ALTER TABLE comunicacion ADD error_envio NVARCHAR(500) NULL
        """,
        # enviado_en: DATETIME NULL
        """
        IF COL_LENGTH('comunicacion', 'enviado_en') IS NULL
            ALTER TABLE comunicacion ADD enviado_en DATETIME NULL
        """,
        # índice compuesto
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_comunicacion_estado_proximo'
              AND object_id = OBJECT_ID('comunicacion')
        )
            CREATE INDEX ix_comunicacion_estado_proximo
                ON comunicacion(estado_entrega, proximo_intento)
        """,
    ]
    for stmt in stmts:
        op.execute(stmt)


def downgrade() -> None:
    stmts = [
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_comunicacion_estado_proximo'
              AND object_id = OBJECT_ID('comunicacion')
        )
            DROP INDEX ix_comunicacion_estado_proximo ON comunicacion
        """,
        """
        IF COL_LENGTH('comunicacion', 'enviado_en') IS NOT NULL
            ALTER TABLE comunicacion DROP COLUMN enviado_en
        """,
        """
        IF COL_LENGTH('comunicacion', 'error_envio') IS NOT NULL
            ALTER TABLE comunicacion DROP COLUMN error_envio
        """,
        """
        IF COL_LENGTH('comunicacion', 'proximo_intento') IS NOT NULL
            ALTER TABLE comunicacion DROP COLUMN proximo_intento
        """,
        """
        IF COL_LENGTH('comunicacion', 'intentos_envio') IS NOT NULL
        BEGIN
            IF EXISTS (
                SELECT 1 FROM sys.default_constraints
                WHERE name = 'DF_comunicacion_intentos_envio'
            )
                ALTER TABLE comunicacion DROP CONSTRAINT DF_comunicacion_intentos_envio
            ALTER TABLE comunicacion DROP COLUMN intentos_envio
        END
        """,
    ]
    for stmt in stmts:
        op.execute(stmt)
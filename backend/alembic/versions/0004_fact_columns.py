"""Añade columnas de filtro/oportunidad en fact_hito_pedido y fact_comunicacion
(idempotente).

Revision ID: 0004_fact_columns
Revises: 0003_outbox_columns
Create Date: 2025-01-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0004_fact_columns"
down_revision: Union[str, None] = "0003_outbox_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    stmts = [
        """
        IF COL_LENGTH('fact_hito_pedido', 'notificado_oportuno') IS NULL
            ALTER TABLE fact_hito_pedido ADD notificado_oportuno BIT NULL
        """,
        """
        IF COL_LENGTH('fact_hito_pedido', 'origen') IS NULL
            ALTER TABLE fact_hito_pedido ADD origen NVARCHAR(20) NULL
        """,
        """
        IF COL_LENGTH('fact_hito_pedido', 'operador_id') IS NULL
            ALTER TABLE fact_hito_pedido ADD operador_id INT NULL
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_fact_hito_origen'
              AND object_id = OBJECT_ID('fact_hito_pedido')
        )
            CREATE INDEX ix_fact_hito_origen ON fact_hito_pedido(origen)
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_fact_hito_operador'
              AND object_id = OBJECT_ID('fact_hito_pedido')
        )
            CREATE INDEX ix_fact_hito_operador ON fact_hito_pedido(operador_id)
        """,
        """
        IF COL_LENGTH('fact_comunicacion', 'operador_id') IS NULL
            ALTER TABLE fact_comunicacion ADD operador_id INT NULL
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_fact_comunicacion_operador'
              AND object_id = OBJECT_ID('fact_comunicacion')
        )
            CREATE INDEX ix_fact_comunicacion_operador ON fact_comunicacion(operador_id)
        """,
    ]
    for stmt in stmts:
        op.execute(stmt)


def downgrade() -> None:
    stmts = [
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_fact_comunicacion_operador'
              AND object_id = OBJECT_ID('fact_comunicacion')
        )
            DROP INDEX ix_fact_comunicacion_operador ON fact_comunicacion
        """,
        """
        IF COL_LENGTH('fact_comunicacion', 'operador_id') IS NOT NULL
            ALTER TABLE fact_comunicacion DROP COLUMN operador_id
        """,
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_fact_hito_operador'
              AND object_id = OBJECT_ID('fact_hito_pedido')
        )
            DROP INDEX ix_fact_hito_operador ON fact_hito_pedido
        """,
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_fact_hito_origen'
              AND object_id = OBJECT_ID('fact_hito_pedido')
        )
            DROP INDEX ix_fact_hito_origen ON fact_hito_pedido
        """,
        """
        IF COL_LENGTH('fact_hito_pedido', 'operador_id') IS NOT NULL
            ALTER TABLE fact_hito_pedido DROP COLUMN operador_id
        """,
        """
        IF COL_LENGTH('fact_hito_pedido', 'origen') IS NOT NULL
            ALTER TABLE fact_hito_pedido DROP COLUMN origen
        """,
        """
        IF COL_LENGTH('fact_hito_pedido', 'notificado_oportuno') IS NOT NULL
            ALTER TABLE fact_hito_pedido DROP COLUMN notificado_oportuno
        """,
    ]
    for stmt in stmts:
        op.execute(stmt)
"""Añade claves únicas para evitar alertas y comunicaciones duplicadas."""
from typing import Sequence, Union

from alembic import op


revision: str = "0011_idempotency_keys"
down_revision: Union[str, None] = "0010_comunicacion_clase"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF COL_LENGTH(N'comunicacion', N'dedupe_key') IS NULL
            ALTER TABLE comunicacion ADD dedupe_key NVARCHAR(160) NULL;
    """)
    op.execute("""
        WITH duplicadas AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY item_hito_id, tipo
                       ORDER BY id
                   ) AS fila
            FROM alerta
            WHERE item_hito_id IS NOT NULL AND estado = 'ABIERTA'
        )
        UPDATE a
        SET estado = 'CERRADA', fecha_atencion = GETUTCDATE()
        FROM alerta a
        JOIN duplicadas d ON d.id = a.id
        WHERE d.fila > 1;
    """)
    op.execute("""
        WITH duplicadas AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       PARTITION BY pedido_id, tipo
                       ORDER BY id
                   ) AS fila
            FROM alerta
            WHERE item_hito_id IS NULL AND estado = 'ABIERTA'
        )
        UPDATE a
        SET estado = 'CERRADA', fecha_atencion = GETUTCDATE()
        FROM alerta a
        JOIN duplicadas d ON d.id = a.id
        WHERE d.fila > 1;
    """)
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = N'uq_comunicacion_dedupe_key'
              AND object_id = OBJECT_ID(N'comunicacion')
        )
            CREATE UNIQUE INDEX uq_comunicacion_dedupe_key
                ON comunicacion(dedupe_key)
                WHERE dedupe_key IS NOT NULL;
    """)
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = N'uq_alerta_hito_tipo_abierta'
              AND object_id = OBJECT_ID(N'alerta')
        )
            CREATE UNIQUE INDEX uq_alerta_hito_tipo_abierta
                ON alerta(item_hito_id, tipo)
                WHERE item_hito_id IS NOT NULL AND estado = 'ABIERTA';
    """)
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = N'uq_alerta_pedido_tipo_abierta'
              AND object_id = OBJECT_ID(N'alerta')
        )
            CREATE UNIQUE INDEX uq_alerta_pedido_tipo_abierta
                ON alerta(pedido_id, tipo)
                WHERE item_hito_id IS NULL AND estado = 'ABIERTA';
    """)


def downgrade() -> None:
    for name, table in (
        ("uq_alerta_pedido_tipo_abierta", "alerta"),
        ("uq_alerta_hito_tipo_abierta", "alerta"),
        ("uq_comunicacion_dedupe_key", "comunicacion"),
    ):
        op.execute(f"""
            IF EXISTS (
                SELECT 1 FROM sys.indexes
                WHERE name = N'{name}' AND object_id = OBJECT_ID(N'{table}')
            )
                DROP INDEX {name} ON {table};
        """)
    op.execute("""
        IF COL_LENGTH(N'comunicacion', N'dedupe_key') IS NOT NULL
            ALTER TABLE comunicacion DROP COLUMN dedupe_key;
    """)

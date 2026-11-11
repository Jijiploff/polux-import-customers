"""Añade canal TELEGRAM, columna telegram_chat_id en cliente y dim_canal.

Cambios:
- cliente.telegram_chat_id (NVARCHAR(40) NULL, index) para vincular chats.
- CHECK constraints de `canal` en `comunicacion` y `plantilla_mensaje`
  ampliados para aceptar 'TELEGRAM'.
- Fila 'TELEGRAM' en `dim_canal` (idempotente) para que el ETL de hechos
  no deje `fact_comunicacion.canal_id` en NULL.

Revision ID: 0007_telegram_channel
Revises: 0006_dimensional_kpi_views
Create Date: 2026-11-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_telegram_channel"
down_revision: Union[str, None] = "0006_dimensional_kpi_views"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Helpers para reconstruir los CHECK constraints del enum `canal`
# ---------------------------------------------------------------------------
def _drop_canal_checks(table: str) -> None:
    """Elimina cualquier CHECK constraint que mencione la columna 'canal'."""
    op.execute(f"""
    DECLARE @name NVARCHAR(255);
    DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT name FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'{table}')
          AND definition LIKE N'%canal%';
    OPEN cur;
    FETCH NEXT FROM cur INTO @name;
    WHILE @@FETCH_STATUS = 0
    BEGIN
        EXEC sp_executesql N'ALTER TABLE {table} DROP CONSTRAINT ' + QUOTENAME(@name);
        FETCH NEXT FROM cur INTO @name;
    END
    CLOSE cur;
    DEALLOCATE cur;
    """)


def _add_canal_check(table: str, values: str) -> None:
    op.execute(f"""
    IF NOT EXISTS (
        SELECT 1 FROM sys.check_constraints
        WHERE parent_object_id = OBJECT_ID(N'{table}')
          AND name = N'CK_{table}_canal'
    )
        ALTER TABLE {table} ADD CONSTRAINT CK_{table}_canal
            CHECK (canal IN ({values}));
    """)


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------
def upgrade() -> None:
    # 1. Columna telegram_chat_id en cliente
    op.execute("""
        IF COL_LENGTH('cliente', 'telegram_chat_id') IS NULL
            ALTER TABLE cliente ADD telegram_chat_id NVARCHAR(40) NULL;
    """)
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_cliente_telegram_chat_id'
              AND object_id = OBJECT_ID('cliente')
        )
            CREATE INDEX ix_cliente_telegram_chat_id ON cliente(telegram_chat_id);
    """)

    # 2. Ampliar CHECK constraints del enum canal
    values = "'WHATSAPP', 'EMAIL', 'WEB', 'TELEGRAM'"
    for table in ("comunicacion", "plantilla_mensaje"):
        _drop_canal_checks(table)
        _add_canal_check(table, values)

    # 3. Fila 'TELEGRAM' en dim_canal (para fact_comunicacion.canal_id)
    op.execute("""
        IF NOT EXISTS (SELECT 1 FROM dim_canal WHERE codigo = 'TELEGRAM')
            INSERT INTO dim_canal (codigo, nombre)
            VALUES ('TELEGRAM', 'Telegram');
    """)


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------
def downgrade() -> None:
    # 1. Eliminar fila TELEGRAM de dim_canal
    op.execute("DELETE FROM dim_canal WHERE codigo = 'TELEGRAM';")

    # 2. Reducir CHECK constraints del enum canal a los 3 valores originales
    values = "'WHATSAPP', 'EMAIL', 'WEB'"
    for table in ("comunicacion", "plantilla_mensaje"):
        _drop_canal_checks(table)
        _add_canal_check(table, values)

    # 3. Eliminar columna e índice de telegram_chat_id
    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ix_cliente_telegram_chat_id'
              AND object_id = OBJECT_ID('cliente')
        )
            DROP INDEX ix_cliente_telegram_chat_id ON cliente;
    """)
    op.execute("""
        IF COL_LENGTH('cliente', 'telegram_chat_id') IS NOT NULL
            ALTER TABLE cliente DROP COLUMN telegram_chat_id;
    """)
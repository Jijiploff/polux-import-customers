"""Vincula chats de Telegram a usuarios operadores.

Cambios:
- usuario.telegram_chat_id (NVARCHAR(40) NULL) con índice único filtrado
  (SQL Server no permite múltiples NULL en un UNIQUE normal).

Revision ID: 0008_usuario_telegram
Revises: 0007_telegram_channel
Create Date: 2026-11-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008_usuario_telegram"
down_revision: Union[str, None] = "0007_telegram_channel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF COL_LENGTH('usuario', 'telegram_chat_id') IS NULL
            ALTER TABLE usuario ADD telegram_chat_id NVARCHAR(40) NULL;
    """)
    op.execute("""
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ux_usuario_telegram_chat_id'
              AND object_id = OBJECT_ID('usuario')
        )
            CREATE UNIQUE INDEX ux_usuario_telegram_chat_id
                ON usuario(telegram_chat_id)
                WHERE telegram_chat_id IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'ux_usuario_telegram_chat_id'
              AND object_id = OBJECT_ID('usuario')
        )
            DROP INDEX ux_usuario_telegram_chat_id ON usuario;
    """)
    op.execute("""
        IF COL_LENGTH('usuario', 'telegram_chat_id') IS NOT NULL
            ALTER TABLE usuario DROP COLUMN telegram_chat_id;
    """)

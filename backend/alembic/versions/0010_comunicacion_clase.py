"""Clasificación de comunicaciones: conversación con el cliente vs. operativo.

- `comunicacion.clase`: `CLIENTE` (hilo con el cliente) u `OPERATIVO`
  (comandos, ayudas, confirmaciones, avisos internos).
- Backfill: los mensajes sin pedido y los textos conocidos del bot pasan a
  `OPERATIVO`; el resto conserva `CLIENTE`.

Revision ID: 0010_comunicacion_clase
Revises: 0009_caso_telegram_reply
Create Date: 2026-11-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0010_comunicacion_clase"
down_revision: Union[str, None] = "0009_caso_telegram_reply"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF COL_LENGTH(N'comunicacion', N'clase') IS NULL
        BEGIN
            ALTER TABLE comunicacion
                ADD clase NVARCHAR(20) NOT NULL
                    CONSTRAINT df_comunicacion_clase DEFAULT N'CLIENTE';
            CREATE INDEX ix_comunicacion_clase ON comunicacion(clase);
        END
    """)

    # Mensajes sin pedido: son registros internos (comandos, ayudas, avisos).
    op.execute("""
        UPDATE comunicacion
        SET clase = N'OPERATIVO'
        WHERE pedido_id IS NULL AND clase = N'CLIENTE';
    """)

    # Textos conocidos del bot que sí quedaron asociados a un pedido.
    op.execute("""
        UPDATE comunicacion
        SET clase = N'OPERATIVO'
        WHERE clase = N'CLIENTE'
          AND (
              contenido LIKE N'👋 Bienvenido a Polux Import%'
              OR contenido LIKE N'✅ Vinculado al pedido%'
              OR contenido LIKE N'✅ Vinculado como operador:%'
              OR contenido LIKE N'✅ Tu chat fue desvinculado%'
              OR contenido LIKE N'✅ Saliste del modo respuesta%'
              OR contenido LIKE N'📋 Casos activos%'
              OR contenido LIKE N'📁 Caso #%'
              OR contenido LIKE N'🚨 Nuevo caso #%'
              OR contenido LIKE N'💬 Mensaje del cliente · Caso #%'
              OR contenido LIKE N'✅ Enviado a %'
              OR contenido LIKE N'✅ Caso #% cerrado%'
              OR contenido LIKE N'⚠️ %'
          );
    """)


def downgrade() -> None:
    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = N'ix_comunicacion_clase'
              AND object_id = OBJECT_ID(N'comunicacion')
        )
            DROP INDEX ix_comunicacion_clase ON comunicacion;
    """)
    op.execute("""
        IF EXISTS (
            SELECT 1 FROM sys.default_constraints
            WHERE name = N'df_comunicacion_clase'
              AND parent_object_id = OBJECT_ID(N'comunicacion')
        )
            ALTER TABLE comunicacion DROP CONSTRAINT df_comunicacion_clase;
    """)
    op.execute("""
        IF COL_LENGTH(N'comunicacion', N'clase') IS NOT NULL
            ALTER TABLE comunicacion DROP COLUMN clase;
    """)

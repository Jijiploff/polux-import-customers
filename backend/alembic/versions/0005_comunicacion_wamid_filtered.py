"""Reemplaza UNIQUE en comunicacion.whatsapp_message_id por índice único filtrado.

SQL Server no admite varios NULL en un constraint UNIQUE: la segunda
comunicación en cola (wamid NULL) violaba la restricción con error 23000 y
rompía toda la ejecución del motor de reglas (bienvenida, avisos, retrasos...).

Se elimina el constraint UNIQUE (nombre autogenerado `UQ__*`) y se crea un
índice único filtrado que solo exige unicidad cuando hay wamid real.

Revision ID: 0005_comunicacion_wamid_filtered
Revises: 0004_fact_columns
Create Date: 2026-11-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_comunicacion_wamid_filtered"
down_revision: Union[str, None] = "0004_fact_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    stmts = [
        """
        DECLARE @uc NVARCHAR(200);
        SELECT TOP 1 @uc = kc.name
        FROM sys.key_constraints kc
        JOIN sys.index_columns ic
             ON ic.object_id = kc.parent_object_id
            AND ic.index_id = kc.unique_index_id
        JOIN sys.columns c
             ON c.object_id = ic.object_id
            AND c.column_id = ic.column_id
        WHERE kc.parent_object_id = OBJECT_ID('comunicacion')
          AND kc.type = 'UQ'
          AND c.name = 'whatsapp_message_id';
        IF @uc IS NOT NULL
            EXEC('ALTER TABLE comunicacion DROP CONSTRAINT [' + @uc + ']');
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'uq_comunicacion_whatsapp_message_id'
              AND object_id = OBJECT_ID('comunicacion')
        )
            CREATE UNIQUE INDEX uq_comunicacion_whatsapp_message_id
                ON comunicacion(whatsapp_message_id)
                WHERE whatsapp_message_id IS NOT NULL;
        """,
    ]
    for stmt in stmts:
        op.execute(stmt)


def downgrade() -> None:
    stmts = [
        """
        IF EXISTS (
            SELECT 1 FROM sys.indexes
            WHERE name = 'uq_comunicacion_whatsapp_message_id'
              AND object_id = OBJECT_ID('comunicacion')
        )
            DROP INDEX uq_comunicacion_whatsapp_message_id ON comunicacion;
        """,
        """
        IF NOT EXISTS (
            SELECT 1 FROM sys.key_constraints kc
            JOIN sys.index_columns ic
                 ON ic.object_id = kc.parent_object_id
                AND ic.index_id = kc.unique_index_id
            JOIN sys.columns c
                 ON c.object_id = ic.object_id
                AND c.column_id = ic.column_id
            WHERE kc.parent_object_id = OBJECT_ID('comunicacion')
              AND kc.type = 'UQ'
              AND c.name = 'whatsapp_message_id'
        )
            ALTER TABLE comunicacion ADD CONSTRAINT UQ_comunicacion_wamid
                UNIQUE (whatsapp_message_id);
        """,
    ]
    for stmt in stmts:
        op.execute(stmt)

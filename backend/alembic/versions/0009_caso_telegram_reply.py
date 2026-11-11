"""Soporte de respuestas de operadores a casos desde Telegram.

Cambios:
- `caso_telegram_notificacion`: mapea (chat_id, message_id) → caso para
  poder responder citando el aviso del caso.
- `usuario_caso_activo`: caso que el operador está atendiendo (flujo tipo
  chat tras pulsar "Responder").

Revision ID: 0009_caso_telegram_reply
Revises: 0008_usuario_telegram
Create Date: 2026-11-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_caso_telegram_reply"
down_revision: Union[str, None] = "0008_usuario_telegram"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        IF OBJECT_ID(N'caso_telegram_notificacion', N'U') IS NULL
        BEGIN
            CREATE TABLE caso_telegram_notificacion (
                id INT IDENTITY(1,1) NOT NULL
                    CONSTRAINT pk_caso_telegram_notificacion PRIMARY KEY,
                caso_id INT NOT NULL,
                usuario_id INT NULL,
                chat_id NVARCHAR(40) NOT NULL,
                message_id BIGINT NOT NULL,
                created_at DATETIME2 NOT NULL
                    CONSTRAINT df_caso_telegram_notificacion_created
                    DEFAULT SYSUTCDATETIME(),
                updated_at DATETIME2 NOT NULL
                    CONSTRAINT df_caso_telegram_notificacion_updated
                    DEFAULT SYSUTCDATETIME(),
                CONSTRAINT uq_caso_telegram_chat_msg UNIQUE (chat_id, message_id),
                CONSTRAINT fk_caso_telegram_notificacion_caso
                    FOREIGN KEY (caso_id) REFERENCES caso_escalamiento(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_caso_telegram_notificacion_usuario
                    FOREIGN KEY (usuario_id) REFERENCES usuario(id)
                    ON DELETE SET NULL
            );
            CREATE INDEX ix_caso_telegram_notificacion_caso
                ON caso_telegram_notificacion(caso_id);
        END
    """)

    op.execute("""
        IF OBJECT_ID(N'usuario_caso_activo', N'U') IS NULL
        BEGIN
            CREATE TABLE usuario_caso_activo (
                usuario_id INT NOT NULL
                    CONSTRAINT pk_usuario_caso_activo PRIMARY KEY,
                caso_id INT NOT NULL,
                created_at DATETIME2 NOT NULL
                    CONSTRAINT df_usuario_caso_activo_created
                    DEFAULT SYSUTCDATETIME(),
                updated_at DATETIME2 NOT NULL
                    CONSTRAINT df_usuario_caso_activo_updated
                    DEFAULT SYSUTCDATETIME(),
                CONSTRAINT fk_usuario_caso_activo_usuario
                    FOREIGN KEY (usuario_id) REFERENCES usuario(id)
                    ON DELETE CASCADE,
                CONSTRAINT fk_usuario_caso_activo_caso
                    FOREIGN KEY (caso_id) REFERENCES caso_escalamiento(id)
                    ON DELETE CASCADE
            );
            CREATE INDEX ix_usuario_caso_activo_caso
                ON usuario_caso_activo(caso_id);
        END
    """)


def downgrade() -> None:
    op.execute("""
        IF OBJECT_ID(N'usuario_caso_activo', N'U') IS NOT NULL
            DROP TABLE usuario_caso_activo;
    """)
    op.execute("""
        IF OBJECT_ID(N'caso_telegram_notificacion', N'U') IS NOT NULL
            DROP TABLE caso_telegram_notificacion;
    """)

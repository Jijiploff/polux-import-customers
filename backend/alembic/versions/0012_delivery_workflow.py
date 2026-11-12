"""Añade datos y auditoría del flujo de entregas con IA y operador."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012_delivery_workflow"
down_revision: Union[str, None] = "0011_idempotency_keys"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coordinacion_entrega",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("chat_id", sa.Unicode(40), nullable=False),
        sa.Column("pedido_id", sa.Integer(), sa.ForeignKey("pedido.id"), nullable=False),
        sa.Column("fase", sa.Unicode(30), nullable=False),
        sa.Column("datos", sa.UnicodeText(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.sysutcdatetime()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.sysutcdatetime()),
        sa.UniqueConstraint("chat_id", name="uq_coordinacion_entrega_chat"),
    )
    columns = [
        ("direccion", sa.Unicode(300), True, None),
        ("distrito", sa.Unicode(120), True, None),
        ("punto_recojo", sa.Unicode(300), True, None),
        ("referencia", sa.Unicode(300), True, None),
        ("receptor_nombre", sa.Unicode(160), True, None),
        ("receptor_dni", sa.Unicode(30), True, None),
        ("receptor_telefono", sa.Unicode(40), True, None),
        ("franja_horaria", sa.Unicode(40), True, None),
        ("notas_courier", sa.UnicodeText(), True, None),
        ("creado_por_agente", sa.Boolean(), False, sa.text("0")),
        ("confirmada_por_id", sa.Integer(), True, None),
        ("fecha_confirmacion", sa.DateTime(), True, None),
        ("motivo_rechazo", sa.UnicodeText(), True, None),
        ("receptor_verificado", sa.Boolean(), False, sa.text("0")),
        ("recibido_por", sa.Unicode(200), True, None),
    ]
    for name, type_, nullable, default in columns:
        op.add_column("entrega", sa.Column(name, type_, nullable=nullable, server_default=default))
    op.create_foreign_key(
        "fk_entrega_confirmada_por_usuario", "entrega", "usuario",
        ["confirmada_por_id"], ["id"],
    )
    op.alter_column("entrega", "creado_por_agente", server_default=None)
    op.alter_column("entrega", "receptor_verificado", server_default=None)


def downgrade() -> None:
    op.drop_table("coordinacion_entrega")
    op.drop_constraint("fk_entrega_confirmada_por_usuario", "entrega", type_="foreignkey")
    for name in (
        "recibido_por", "receptor_verificado", "motivo_rechazo",
        "fecha_confirmacion", "confirmada_por_id", "creado_por_agente",
        "notas_courier", "franja_horaria", "receptor_telefono", "receptor_dni",
        "receptor_nombre", "referencia", "punto_recojo", "distrito", "direccion",
    ):
        op.drop_column("entrega", name)

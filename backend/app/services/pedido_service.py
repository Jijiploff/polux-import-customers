"""Reglas de consulta y recomputación de estado del pedido."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    EstadoItem,
    EstadoPedido,
    ItemHito,
    OrigenItem,
    Pedido,
    PedidoItem,
)

# Orden de "más atrasado primero" para el estado general del pedido.
_ESTADO_RANK = {
    EstadoItem.PENDIENTE: 0,
    EstadoItem.EN_PROCESO: 1,
    EstadoItem.LISTO_PARA_ENTREGA: 2,
    EstadoItem.ENTREGADO: 3,
    EstadoItem.CON_OBSERVACIONES: 4,
}


def list_pedidos(
    db: Session,
    *,
    estado: EstadoPedido | None = None,
    cliente_id: int | None = None,
    origen: OrigenItem | None = None,
    page: int = 1,
    size: int = 20,
):
    stmt = select(Pedido)
    if estado:
        stmt = stmt.where(Pedido.estado_actual == estado)
    if cliente_id:
        stmt = stmt.where(Pedido.cliente_id == cliente_id)
    if origen:
        stmt = stmt.where(
            Pedido.id.in_(
                select(PedidoItem.pedido_id).where(PedidoItem.origen == origen)
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Pedido.fecha_ingreso.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return rows, total


def get_pedido(db: Session, pedido_id: int) -> Pedido | None:
    """Carga pedido con cliente, ítems, hitos e `hito` de cada hito.

    El eager-load de `ItemHito.hito` es OBLIGATORIO para que el
    `ItemHitoRead._fill_hito_fields` funcione al serializar anidado.
    """
    return db.scalar(
        select(Pedido)
        .options(
            selectinload(Pedido.cliente),
            selectinload(Pedido.items)
            .selectinload(PedidoItem.hitos)
            .selectinload(ItemHito.hito),
        )
        .where(Pedido.id == pedido_id)
    )


def _estado_por_items(items: list[PedidoItem]) -> EstadoItem:
    """El estado general del pedido es el del ítem MÁS ATRASADO (§2.1 del prompt)."""
    if not items:
        return EstadoItem.PENDIENTE
    return min((i.estado for i in items), key=lambda e: _ESTADO_RANK[e])


def recompute_pedido_estado(db: Session, pedido: Pedido) -> Pedido:
    """Recalcula `estado_actual` a partir de los estados de sus ítems.

    Reglas:
    - Si el pedido está en estado terminal o en coordinación, no lo alteramos.
    - Todos los ítems LISTO_PARA_ENTREGA → LISTO_PARA_ENTREGA.
    - Todos PENDIENTE → RECIBIDO.
    - Resto → EN_PROCESO.
    """
    estado_item = _estado_por_items(pedido.items)
    if estado_item == EstadoItem.LISTO_PARA_ENTREGA:
        nuevo = EstadoPedido.LISTO_PARA_ENTREGA
    elif estado_item == EstadoItem.PENDIENTE:
        nuevo = EstadoPedido.RECIBIDO
    else:
        nuevo = EstadoPedido.EN_PROCESO

    if pedido.estado_actual in {
        EstadoPedido.ENTREGADO,
        EstadoPedido.CERRADO,
        EstadoPedido.CERRADO_CON_OBSERVACIONES,
        EstadoPedido.CANCELADO,
        EstadoPedido.EN_COORDINACION,
    }:
        return pedido
    pedido.estado_actual = nuevo
    return pedido
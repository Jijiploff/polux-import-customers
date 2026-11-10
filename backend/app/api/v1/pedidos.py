"""Endpoints de pedidos: listar, detalle completo."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import EstadoPedido, OrigenItem
from app.schemas.common import Page
from app.schemas.pedido import (
    PedidoDetail,
    PedidoFullDetail,
    PedidoRead,
)
from app.services.pedido_service import get_pedido, list_pedidos

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=Page[PedidoRead], summary="Listar pedidos")
def listar(
    estado: EstadoPedido | None = Query(None),
    cliente_id: int | None = Query(None),
    origen: OrigenItem | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows, total = list_pedidos(
        db, estado=estado, cliente_id=cliente_id, origen=origen, page=page, size=size
    )
    return Page[PedidoRead](items=rows, total=total, page=page, size=size)


@router.get("/{pedido_id}", response_model=PedidoDetail, summary="Detalle de pedido (con ítems)")
def detalle(pedido_id: int, db: Session = Depends(get_db)):
    p = get_pedido(db, pedido_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    return p


@router.get("/{pedido_id}/full", response_model=PedidoFullDetail, summary="Pedido completo (ítems + hitos)")
def detalle_full(pedido_id: int, db: Session = Depends(get_db)):
    p = get_pedido(db, pedido_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    return p
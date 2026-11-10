"""Actualización de estado de un ítem (operador)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_operador
from app.db.session import get_db
from app.models import PedidoItem
from app.schemas.pedido import ItemEstadoUpdate, PedidoItemRead
from app.services.pedido_service import recompute_pedido_estado

router = APIRouter()


@router.patch(
    "/{item_id}/estado",
    response_model=PedidoItemRead,
    summary="Actualiza el estado de un ítem",
)
def actualizar_estado(
    item_id: int,
    payload: ItemEstadoUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    item = db.get(PedidoItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ítem no encontrado")
    item.estado = payload.estado
    item.updated_by_id = current.id
    recompute_pedido_estado(db, item.pedido)
    db.commit()
    db.refresh(item)
    return item
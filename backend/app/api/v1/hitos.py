"""Consulta y marcado de hitos de ítem."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_operador
from app.db.session import get_db
from app.models import ItemHito
from app.schemas.pedido import HitoCompletar, HitoRead, ItemHitoRead
from app.services.hito_service import list_hitos_por_item, marcar_completado

router = APIRouter()


def _serialize(ih: ItemHito) -> ItemHitoRead:
    return ItemHitoRead(
        id=ih.id,
        hito_id=ih.hito_id,
        hito_codigo=ih.hito.codigo if ih.hito else "",
        hito_nombre=ih.hito.nombre if ih.hito else "",
        fecha_prevista=ih.fecha_prevista,
        fecha_real=ih.fecha_real,
        estado=ih.estado,
        dias_atraso=ih.dias_atraso,
        notificado_cliente=ih.notificado_cliente,
    )


@router.get(
    "/por-item/{pedido_item_id}",
    response_model=list[ItemHitoRead],
    dependencies=[Depends(get_current_user)],
)
def listar_por_item(pedido_item_id: int, db: Session = Depends(get_db)):
    return [_serialize(ih) for ih in list_hitos_por_item(db, pedido_item_id)]


@router.post(
    "/{item_hito_id}/completar",
    response_model=HitoRead,
    dependencies=[Depends(require_operador)],
)
def completar(
    item_hito_id: int,
    payload: HitoCompletar,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    ih = marcar_completado(
        db, item_hito_id, fecha_real=payload.fecha_real, usuario_id=current.id
    )
    return ih
"""Creación, autorización y finalización de entregas.

Regla inviolable: la entrega parcial exige autorización humana registrada.
Validada en servicio Y en BD (CHECK).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.deps import get_current_user, require_operador
from app.db.session import get_db
from app.models import Entrega
from app.schemas.entrega import EntregaCompletar, EntregaCreate, EntregaRead
from app.services.entrega_service import completar_entrega, crear_entrega

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[EntregaRead], summary="Listar entregas de un pedido")
def listar(pedido_id: int, db: Session = Depends(get_db)):
    return db.scalars(
        select(Entrega)
        .options(selectinload(Entrega.items))
        .where(Entrega.pedido_id == pedido_id)
        .order_by(Entrega.id)
    ).all()

@router.post(
    "",
    response_model=EntregaRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_operador)],
)
def crear(payload: EntregaCreate, db: Session = Depends(get_db), current=Depends(require_operador)):
    return crear_entrega(db, payload, usuario_id=current.id)


@router.post(
    "/{entrega_id}/completar",
    response_model=EntregaRead,
    dependencies=[Depends(require_operador)],
)
def completar(
    entrega_id: int,
    payload: EntregaCompletar,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    return completar_entrega(
        db,
        entrega_id,
        fecha_real=payload.fecha_real,
        conformidades=payload.conformidades,
        usuario_id=current.id,
    )
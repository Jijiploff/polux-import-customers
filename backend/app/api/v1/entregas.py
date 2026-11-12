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
from app.models import EstadoEntrega
from app.schemas.entrega import (
    EntregaCompletar, EntregaCreate, EntregaRead, EntregaRechazar, EntregaUpdate,
)
from app.services.entrega_service import (
    actualizar_entrega, cambiar_estado_entrega, completar_entrega,
    confirmar_entrega, crear_entrega, rechazar_entrega,
)

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[EntregaRead], summary="Listar entregas")
def listar(
    pedido_id: int | None = None,
    estado: EstadoEntrega | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(Entrega).options(selectinload(Entrega.items)).order_by(Entrega.id.desc())
    if pedido_id is not None:
        stmt = stmt.where(Entrega.pedido_id == pedido_id)
    if estado is not None:
        stmt = stmt.where(Entrega.estado == estado)
    return db.scalars(stmt).all()


@router.get("/{entrega_id}", response_model=EntregaRead, summary="Detalle de entrega")
def detalle(entrega_id: int, db: Session = Depends(get_db)):
    entrega = db.scalar(
        select(Entrega)
        .options(selectinload(Entrega.items))
        .where(Entrega.id == entrega_id)
    )
    if entrega is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Entrega no encontrada")
    return entrega

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
        receptor_verificado=payload.receptor_verificado,
        recibido_por=payload.recibido_por,
        usuario_id=current.id,
    )


@router.patch("/{entrega_id}", response_model=EntregaRead, dependencies=[Depends(require_operador)])
def actualizar(
    entrega_id: int,
    payload: EntregaUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    return actualizar_entrega(db, entrega_id, payload, usuario_id=current.id)


@router.post(
    "/{entrega_id}/confirmar",
    response_model=EntregaRead,
    dependencies=[Depends(require_operador)],
)
def confirmar(entrega_id: int, db: Session = Depends(get_db), current=Depends(require_operador)):
    return confirmar_entrega(db, entrega_id, usuario_id=current.id)


@router.post(
    "/{entrega_id}/rechazar",
    response_model=EntregaRead,
    dependencies=[Depends(require_operador)],
)
def rechazar(
    entrega_id: int,
    payload: EntregaRechazar,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    return rechazar_entrega(db, entrega_id, payload.motivo, usuario_id=current.id)


@router.post(
    "/{entrega_id}/estado/{estado}",
    response_model=EntregaRead,
    dependencies=[Depends(require_operador)],
)
def cambiar_estado(
    entrega_id: int,
    estado: EstadoEntrega,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    return cambiar_estado_entrega(db, entrega_id, estado, usuario_id=current.id)
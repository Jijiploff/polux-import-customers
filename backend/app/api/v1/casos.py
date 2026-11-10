"""Casos de escalamiento."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_operador
from app.db.session import get_db
from app.models import CasoEscalamiento, EstadoCaso
from app.schemas.comms import CasoCreate, CasoRead, CasoUpdate
from app.services.caso_service import actualizar_caso, crear_caso

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[CasoRead])
def listar(
    estado: EstadoCaso | None = Query(None),
    pedido_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(CasoEscalamiento).order_by(CasoEscalamiento.id.desc())
    if estado:
        stmt = stmt.where(CasoEscalamiento.estado == estado)
    if pedido_id:
        stmt = stmt.where(CasoEscalamiento.pedido_id == pedido_id)
    return db.scalars(stmt).all()


@router.post("", response_model=CasoRead, dependencies=[Depends(require_operador)])
def crear(payload: CasoCreate, db: Session = Depends(get_db), current=Depends(require_operador)):
    return crear_caso(db, payload, usuario_id=current.id)


@router.patch("/{caso_id}", response_model=CasoRead, dependencies=[Depends(require_operador)])
def actualizar(
    caso_id: int,
    payload: CasoUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    return actualizar_caso(db, caso_id, payload, usuario_id=current.id)
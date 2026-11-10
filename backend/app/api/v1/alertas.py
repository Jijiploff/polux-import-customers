"""Consulta de alertas + atención / actualización por operador."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_operador
from app.db.session import get_db
from app.models import Alerta, EstadoAlerta
from app.schemas.comms import AlertaRead, AlertaUpdate

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[AlertaRead])
def listar(
    estado: EstadoAlerta | None = Query(None),
    pedido_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(Alerta).order_by(Alerta.id.desc())
    if estado:
        stmt = stmt.where(Alerta.estado == estado)
    if pedido_id:
        stmt = stmt.where(Alerta.pedido_id == pedido_id)
    return db.scalars(stmt).all()


@router.patch(
    "/{alerta_id}/atender",
    response_model=AlertaRead,
    dependencies=[Depends(require_operador)],
    summary="Marcar alerta como atendida",
)
def atender(
    alerta_id: int,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
    if alerta.estado == EstadoAlerta.CERRADA:
        raise HTTPException(status.HTTP_409_CONFLICT, "La alerta ya está cerrada")
    alerta.estado = EstadoAlerta.ATENDIDA
    alerta.fecha_atencion = datetime.utcnow()
    alerta.updated_by_id = current.id
    db.commit()
    db.refresh(alerta)
    return alerta


@router.patch(
    "/{alerta_id}",
    response_model=AlertaRead,
    dependencies=[Depends(require_operador)],
    summary="Actualizar estado de alerta (atendida / cerrada / ignorada)",
)
def actualizar(
    alerta_id: int,
    payload: AlertaUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    alerta = db.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta no encontrada")
    if alerta.estado == EstadoAlerta.CERRADA:
        raise HTTPException(status.HTTP_409_CONFLICT, "La alerta ya está cerrada")
    alerta.estado = payload.estado
    if payload.estado == EstadoAlerta.ATENDIDA and alerta.fecha_atencion is None:
        alerta.fecha_atencion = datetime.utcnow()
    alerta.updated_by_id = current.id
    db.commit()
    db.refresh(alerta)
    return alerta
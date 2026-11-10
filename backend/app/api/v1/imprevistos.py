"""Imprevistos: registro, actualización de estado, cierre."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_operador
from app.db.session import get_db
from app.models import EstadoImprevisto, Imprevisto
from app.schemas.comms import ImprevistoCreate, ImprevistoRead, ImprevistoUpdate

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ImprevistoRead])
def listar(
    estado: EstadoImprevisto | None = Query(None),
    pedido_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    stmt = select(Imprevisto).order_by(Imprevisto.id.desc())
    if estado:
        stmt = stmt.where(Imprevisto.estado == estado)
    if pedido_id:
        stmt = stmt.where(Imprevisto.pedido_id == pedido_id)
    return db.scalars(stmt).all()


@router.post("", response_model=ImprevistoRead, dependencies=[Depends(require_operador)])
def crear(payload: ImprevistoCreate, db: Session = Depends(get_db), current=Depends(require_operador)):
    obj = Imprevisto(
        pedido_id=payload.pedido_id,
        pedido_item_id=payload.pedido_item_id,
        tipo=payload.tipo,
        descripcion=payload.descripcion,
        fecha_deteccion=payload.fecha_deteccion,
        estado=EstadoImprevisto.ABIERTO,
        created_by_id=current.id,
        updated_by_id=current.id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/{imprevisto_id}", response_model=ImprevistoRead,
              dependencies=[Depends(require_operador)])
def actualizar(
    imprevisto_id: int,
    payload: ImprevistoUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_operador),
):
    obj = db.get(Imprevisto, imprevisto_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Imprevisto no encontrado")
    if payload.estado in {EstadoImprevisto.RESUELTO, EstadoImprevisto.CERRADO} and not payload.fecha_resolucion:
        payload = payload.model_copy(update={"fecha_resolucion": datetime.utcnow()})
    obj.estado = payload.estado
    if payload.resolucion is not None:
        obj.resolucion = payload.resolucion
    if payload.fecha_resolucion is not None:
        obj.fecha_resolucion = payload.fecha_resolucion
    obj.updated_by_id = current.id
    db.commit()
    db.refresh(obj)
    return obj
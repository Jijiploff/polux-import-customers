"""Registro y consulta de comunicaciones (usadas por el agente y por operadores)."""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_operador
from app.db.session import get_db
from app.models import Comunicacion
from app.schemas.comms import ComunicacionCreate, ComunicacionRead

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ComunicacionRead])
def listar(
    pedido_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(Comunicacion).order_by(Comunicacion.fecha.desc())
    if pedido_id:
        stmt = stmt.where(Comunicacion.pedido_id == pedido_id)
    return db.scalars(stmt.offset((page - 1) * size).limit(size)).all()


@router.post("", response_model=ComunicacionRead, dependencies=[Depends(require_operador)])
def crear(payload: ComunicacionCreate, db: Session = Depends(get_db), current=Depends(require_operador)):
    obj = Comunicacion(
        pedido_id=payload.pedido_id,
        pedido_item_id=payload.pedido_item_id,
        direccion=payload.direccion,
        canal=payload.canal,
        contenido=payload.contenido,
        intencion_detectada=payload.intencion_detectada,
        sentimiento=payload.sentimiento,
        autor=payload.autor,
        plantilla_id=payload.plantilla_id,
        escalado=payload.escalado,
        fecha=payload.fecha or datetime.utcnow(),
        created_by_id=current.id,
        updated_by_id=current.id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
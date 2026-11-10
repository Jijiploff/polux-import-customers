"""Consulta y actualización de reglas de negocio (ADMIN escribe)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.db.session import get_db
from app.models import ReglaNegocio
from app.schemas.admin import ReglaRead, ReglaUpdate

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[ReglaRead])
def listar(db: Session = Depends(get_db)):
    return db.scalars(select(ReglaNegocio).order_by(ReglaNegocio.categoria, ReglaNegocio.codigo)).all()


@router.patch("/{regla_id}", response_model=ReglaRead, dependencies=[Depends(require_admin)])
def actualizar(
    regla_id: int,
    payload: ReglaUpdate,
    db: Session = Depends(get_db),
    current=Depends(require_admin),
):
    obj = db.get(ReglaNegocio, regla_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Regla no encontrada")
    if payload.valor is not None:
        obj.valor = payload.valor
    if payload.activo is not None:
        obj.activo = payload.activo
    obj.updated_by_id = current.id
    db.commit()
    db.refresh(obj)
    return obj
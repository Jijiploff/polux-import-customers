"""Gestión de casos de escalamiento: primera acción y cierre."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import CasoEscalamiento, EstadoCaso
from app.schemas.comms import CasoCreate, CasoUpdate


def crear_caso(db: Session, payload: CasoCreate, *, usuario_id: int) -> CasoEscalamiento:
    caso = CasoEscalamiento(
        pedido_id=payload.pedido_id,
        motivo=payload.motivo,
        prioridad=payload.prioridad,
        descripcion=payload.descripcion,
        fecha_apertura=datetime.utcnow(),
        estado=EstadoCaso.ABIERTO,
        created_by_id=usuario_id,
        updated_by_id=usuario_id,
    )
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


def actualizar_caso(
    db: Session, caso_id: int, payload: CasoUpdate, *, usuario_id: int
) -> CasoEscalamiento:
    caso = db.get(CasoEscalamiento, caso_id)
    if caso is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Caso no encontrado")
    if caso.estado == EstadoCaso.CERRADO:
        raise HTTPException(status.HTTP_409_CONFLICT, "El caso ya está cerrado")

    if payload.registrar_primera_accion and caso.fecha_primera_accion is None:
        caso.fecha_primera_accion = datetime.utcnow()
        if caso.estado == EstadoCaso.ABIERTO:
            caso.estado = EstadoCaso.EN_PROCESO

    if payload.responsable_id is not None:
        caso.responsable_id = payload.responsable_id

    if payload.estado is not None:
        # Regla: no cerrar sin primera acción (trazabilidad mínima)
        if payload.estado == EstadoCaso.CERRADO:
            if caso.fecha_primera_accion is None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "No se puede cerrar un caso sin registrar la primera acción humana",
                )
            caso.fecha_cierre = datetime.utcnow()
        caso.estado = payload.estado

    caso.updated_by_id = usuario_id
    db.commit()
    db.refresh(caso)
    return caso
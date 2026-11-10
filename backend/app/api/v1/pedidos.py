"""Endpoints de pedidos: listar, detalle completo, línea de tiempo."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import EstadoPedido, OrigenItem
from app.schemas.common import Page
from app.schemas.pedido import (
    PedidoDetail,
    PedidoFullDetail,
    PedidoRead,
)
from app.schemas.timeline import TIPOS_EVENTO, TimelineRead
from app.services.pedido_service import get_pedido, list_pedidos
from app.services.timeline_service import build_timeline

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=Page[PedidoRead], summary="Listar pedidos")
def listar(
    estado: EstadoPedido | None = Query(None),
    cliente_id: int | None = Query(None),
    origen: OrigenItem | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows, total = list_pedidos(
        db, estado=estado, cliente_id=cliente_id, origen=origen, page=page, size=size
    )
    return Page[PedidoRead](items=rows, total=total, page=page, size=size)


@router.get("/{pedido_id}", response_model=PedidoDetail, summary="Detalle de pedido (con ítems)")
def detalle(pedido_id: int, db: Session = Depends(get_db)):
    p = get_pedido(db, pedido_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    return p


@router.get("/{pedido_id}/full", response_model=PedidoFullDetail, summary="Pedido completo (ítems + hitos)")
def detalle_full(pedido_id: int, db: Session = Depends(get_db)):
    p = get_pedido(db, pedido_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    return p


@router.get(
    "/{pedido_id}/timeline",
    response_model=TimelineRead,
    summary="Línea de tiempo del pedido (hitos, mensajes, casos, imprevistos, entregas, alertas)",
)
def timeline(
    pedido_id: int,
    incluir_mensajes: bool = Query(
        False,
        description="Incluye todos los mensajes; por defecto solo eventos clave "
        "(quejas/escalamientos, respuestas del asesor y avisos con plantilla)",
    ),
    tipos: str | None = Query(
        None,
        description="Filtro por tipos separados por coma: "
        + ",".join(TIPOS_EVENTO),
    ),
    desde: datetime | None = Query(None, description="Fecha mínima del evento (UTC)"),
    hasta: datetime | None = Query(None, description="Fecha máxima del evento (UTC)"),
    limit: int = Query(200, ge=1, le=500, description="Máximo de eventos (más recientes primero)"),
    db: Session = Depends(get_db),
):
    """Historia del pedido en una sola lista ordenada (más reciente primero).

    Solo lectura: no escribe datos ni dispara el motor de reglas.
    """
    p = get_pedido(db, pedido_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido no encontrado")
    tipos_set: set[str] | None = None
    if tipos:
        tipos_set = {t.strip() for t in tipos.split(",") if t.strip()}
        desconocidos = tipos_set - set(TIPOS_EVENTO)
        if desconocidos:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Tipos desconocidos: " + ", ".join(sorted(desconocidos)),
            )
    return build_timeline(
        db,
        p,
        incluir_mensajes=incluir_mensajes,
        tipos=tipos_set,
        desde=desde,
        hasta=hasta,
        limit=limit,
    )
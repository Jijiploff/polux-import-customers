"""Marcado de hitos completados y detección de atrasos."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    EstadoHito,
    EstadoItem,
    HitoCatalogo,
    ItemHito,
    OrigenItem,
    Pedido,
    PedidoItem,
)
from app.services.pedido_service import recompute_pedido_estado
from app.services.notification_service import NotificationService
from app.services.outbox_worker import OutboxWorker


def get_item_hito(db: Session, item_hito_id: int) -> ItemHito:
    obj = db.get(ItemHito, item_hito_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Hito de ítem no encontrado")
    return obj


def list_hitos_por_item(db: Session, pedido_item_id: int) -> list[ItemHito]:
    return db.scalars(
        select(ItemHito).where(ItemHito.pedido_item_id == pedido_item_id).order_by(ItemHito.id)
    ).all()


def marcar_completado(
    db: Session,
    item_hito_id: int,
    *,
    fecha_real: datetime,
    usuario_id: int | None,
) -> ItemHito:
    """Marca un hito como COMPLETADO y propaga al ítem y al pedido."""
    ih = get_item_hito(db, item_hito_id)
    if ih.estado == EstadoHito.COMPLETADO:
        raise HTTPException(status.HTTP_409_CONFLICT, "El hito ya estaba completado")

    ih.fecha_real = fecha_real
    ih.estado = EstadoHito.COMPLETADO
    ih.updated_by_id = usuario_id

    item: PedidoItem = ih.item
    hito: HitoCatalogo = ih.hito

    # Detectar si este es el último hito del ítem (por orden)
    pendientes = db.scalar(
        select(ItemHito)
        .join(HitoCatalogo, HitoCatalogo.id == ItemHito.hito_id)
        .where(
            ItemHito.pedido_item_id == item.id,
            ItemHito.estado != EstadoHito.COMPLETADO,
            ItemHito.id != ih.id,
        )
    )
    if pendientes is None:
        item.estado = EstadoItem.LISTO_PARA_ENTREGA
    else:
        item.estado = EstadoItem.EN_PROCESO

    pedido: Pedido = item.pedido
    recompute_pedido_estado(db, pedido)
    _notificar_hito_completado(db, ih, pedido, usuario_id)
    db.commit()
    db.refresh(ih)
    return ih


def _notificar_hito_completado(
    db: Session,
    ih: ItemHito,
    pedido: Pedido,
    usuario_id: int | None,
) -> None:
    """Envía el aviso inmediatamente cuando el cliente tiene Telegram vinculado.

    El motor de reglas mantiene la notificación de otros canales y el reintento
    periódico. Aquí se despacha el outbox en la misma operación para no esperar
    al siguiente ciclo del scheduler.
    """
    cliente = pedido.cliente
    if cliente is None or not cliente.telegram_chat_id:
        return

    comunicacion = NotificationService(db).send_from_template(
        codigo_plantilla="AVISO_HITO",
        pedido=pedido,
        variables={
            "cliente_nombre": cliente.nombre,
            "pedido_codigo": pedido.codigo,
            "hito_nombre": ih.hito.nombre,
            "items_afectados": ih.item.descripcion_producto,
            "fecha_prometida": pedido.fecha_prometida.strftime("%d/%m/%Y"),
        },
        usuario_id=usuario_id,
    )
    if comunicacion is None:
        return

    OutboxWorker(db).process_communication(comunicacion.id)
    ih.notificado_cliente = True
    ih.fecha_notificacion = datetime.utcnow()


def registrar_atrasos(db: Session, ahora: datetime | None = None) -> int:
    """Recalcula `dias_atraso` para hitos pendientes con fecha_prevista vencida.

    No dispara alertas (eso corresponde al motor de reglas de Fase 3).
    """
    ahora = ahora or datetime.utcnow()
    updated = 0
    rows = db.scalars(
        select(ItemHito).where(
            ItemHito.estado.in_([EstadoHito.PENDIENTE, EstadoHito.EN_PROCESO]),
            ItemHito.fecha_prevista.is_not(None),
            ItemHito.fecha_prevista < ahora,
        )
    ).all()
    for ih in rows:
        delta = (ahora - ih.fecha_prevista).days
        if delta > 0:
            ih.dias_atraso = delta
            ih.estado = EstadoHito.ATRASADO
            updated += 1
    if updated:
        db.commit()
    return updated
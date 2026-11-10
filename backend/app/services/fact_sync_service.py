"""ETL idempotente hacia el modelo dimensional.

Sincroniza las tablas `fact_*` y `dim_*` desde el operacional. Cada `_sync_*`
usa la clave natural de la tabla de hechos (`item_hito_id`, `comunicacion_id`,
`caso_id`, `imprevisto_id`, `entrega_id`) como idempotencia: un registro ya
sincronizado no se duplica.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import (
    Canal,
    CasoEscalamiento,
    Comunicacion,
    Conformidad,
    DimCanal,
    DimHito,
    DimProducto,
    DimTiempo,
    DimTipoImprevisto,
    Entrega,
    EntregaItem,
    EstadoEntrega,
    EstadoHito,
    FactComunicacion,
    FactEntrega,
    FactEscalamiento,
    FactHitoPedido,
    FactImprevisto,
    HitoCatalogo,
    Imprevisto,
    ItemHito,
    Pedido,
    PedidoItem,
    Producto,
    ResultadoConformidad,
    TipoImprevisto,
)

logger = get_logger("fact_sync_service")


class FactSyncService:
    def __init__(self, db: Session):
        self.db = db

    def sync_all(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name, fn in [
            ("dim_producto", self._sync_dim_producto),
            ("dim_hito", self._sync_dim_hito),
            ("fact_hito_pedido", self._sync_hitos),
            ("fact_comunicacion", self._sync_comunicaciones),
            ("fact_escalamiento", self._sync_escalamientos),
            ("fact_imprevisto", self._sync_imprevistos),
            ("fact_entrega", self._sync_entregas),
        ]:
            try:
                counts[name] = fn()
            except Exception:
                logger.exception("fact_sync_failed name=%s", name)
                counts[name] = -1
        self.db.commit()
        logger.info("fact_sync_done counts=%s", counts)
        return counts

    # ===================== DIMENSIONES =====================
    def _sync_dim_producto(self) -> int:
        inserted = 0
        for p in self.db.scalars(select(Producto).where(Producto.activo== True)).all():
            exists = self.db.scalar(select(DimProducto.id).where(DimProducto.sku == p.sku))
            if exists:
                continue
            self.db.add(DimProducto(
                producto_id=p.id, sku=p.sku, nombre=p.nombre, categoria=p.categoria.value,
            ))
            inserted += 1
        return inserted

    def _sync_dim_hito(self) -> int:
        inserted = 0
        for h in self.db.scalars(select(HitoCatalogo)).all():
            exists = self.db.scalar(select(DimHito.id).where(DimHito.codigo == h.codigo))
            if exists:
                continue
            self.db.add(DimHito(
                hito_id=h.id, codigo=h.codigo, nombre=h.nombre, origen=h.origen.value,
            ))
            inserted += 1
        return inserted

    # ===================== HECHOS =====================
    def _sync_hitos(self) -> int:
        from app.models import OrigenItem

        rows = self.db.execute(
            select(ItemHito, PedidoItem, DimHito.id, DimProducto.id)
            .join(PedidoItem, PedidoItem.id == ItemHito.pedido_item_id)
            .join(HitoCatalogo, HitoCatalogo.id == ItemHito.hito_id)
            .outerjoin(DimHito, DimHito.codigo == HitoCatalogo.codigo)
            .outerjoin(DimProducto, DimProducto.producto_id == PedidoItem.producto_id)
            .where(ItemHito.estado == EstadoHito.COMPLETADO)
            .where(~select(FactHitoPedido.id)
                   .where(FactHitoPedido.item_hito_id == ItemHito.id)
                   .exists())
        ).all()

        inserted = 0
        for ih, item, dim_hito_id, dim_prod_id in rows:
            # tiempo_id según fecha_real (fallback a fecha_prevista)
            fecha_ref = ih.fecha_real or ih.fecha_prevista
            tiempo_id = _tiempo_id(fecha_ref) if fecha_ref else None

            notificado_oportuno: bool | None = None
            if ih.fecha_real and ih.fecha_notificacion:
                delta_hours = (ih.fecha_notificacion - ih.fecha_real).total_seconds() / 3600
                notificado_oportuno = delta_hours <= 2
            elif ih.notificado_cliente:
                notificado_oportuno = False  # notificado pero sin fecha; asumir no oportuno

            self.db.add(FactHitoPedido(
                tiempo_id=tiempo_id,
                hito_id=dim_hito_id,
                producto_id=dim_prod_id,
                pedido_id=item.pedido_id,
                pedido_item_id=item.id,
                item_hito_id=ih.id,
                completado=True,
                notificado=ih.notificado_cliente,
                notificado_oportuno=notificado_oportuno,
                dias_atraso=ih.dias_atraso,
                origen=item.origen.value if item.origen else None,
                operador_id=ih.updated_by_id,
            ))
            inserted += 1
        return inserted

    def _sync_comunicaciones(self) -> int:
        canal_map = {c.codigo: c.id for c in self.db.scalars(select(DimCanal)).all()}

        rows = self.db.execute(
            select(Comunicacion)
            .where(~select(FactComunicacion.id)
                   .where(FactComunicacion.comunicacion_id == Comunicacion.id)
                   .exists())
        ).scalars().all()

        inserted = 0
        for c in rows:
            self.db.add(FactComunicacion(
                tiempo_id=_tiempo_id(c.fecha) if c.fecha else None,
                canal_id=canal_map.get(c.canal.value),
                comunicacion_id=c.id,
                pedido_id=c.pedido_id,
                direccion=c.direccion.value,
                autor=c.autor.value,
                escalado=c.escalado,
                sentimiento=c.sentimiento.value if c.sentimiento else None,
                operador_id=c.created_by_id,
            ))
            inserted += 1
        return inserted

    def _sync_escalamientos(self) -> int:
        rows = self.db.execute(
            select(CasoEscalamiento)
            .where(~select(FactEscalamiento.id)
                   .where(FactEscalamiento.caso_id == CasoEscalamiento.id)
                   .exists())
        ).scalars().all()

        inserted = 0
        for caso in rows:
            horas_respuesta: float | None = None
            if caso.fecha_primera_accion and caso.fecha_apertura:
                delta = caso.fecha_primera_accion - caso.fecha_apertura
                horas_respuesta = round(delta.total_seconds() / 3600, 2)
            self.db.add(FactEscalamiento(
                tiempo_id=_tiempo_id(caso.fecha_apertura),
                caso_id=caso.id,
                pedido_id=caso.pedido_id,
                motivo=caso.motivo.value,
                prioridad=caso.prioridad.value,
                horas_respuesta=horas_respuesta,
            ))
            inserted += 1
        return inserted

    def _sync_imprevistos(self) -> int:
        tipo_map = {t.codigo: t.id for t in self.db.scalars(select(DimTipoImprevisto)).all()}

        rows = self.db.execute(
            select(Imprevisto)
            .where(~select(FactImprevisto.id)
                   .where(FactImprevisto.imprevisto_id == Imprevisto.id)
                   .exists())
        ).scalars().all()

        inserted = 0
        for imp in rows:
            dias_res: float | None = None
            if imp.fecha_resolucion and imp.fecha_deteccion:
                delta = imp.fecha_resolucion - imp.fecha_deteccion
                dias_res = round(delta.total_seconds() / 86400, 2)
            self.db.add(FactImprevisto(
                tiempo_id=_tiempo_id(imp.fecha_deteccion),
                tipo_id=tipo_map.get(imp.tipo.value),
                imprevisto_id=imp.id,
                pedido_id=imp.pedido_id,
                dias_resolucion=dias_res,
            ))
            inserted += 1
        return inserted

    def _sync_entregas(self) -> int:
        rows = self.db.execute(
            select(Entrega, Pedido)
            .join(Pedido, Pedido.id == Entrega.pedido_id)
            .where(Entrega.estado == EstadoEntrega.ENTREGADA)
            .where(~select(FactEntrega.id)
                   .where(FactEntrega.entrega_id == Entrega.id)
                   .exists())
        ).all()

        inserted = 0
        for e, ped in rows:
            a_tiempo = bool(e.fecha_real and ped.fecha_prometida and e.fecha_real <= ped.fecha_prometida)
            con_obs = self.db.scalar(
                select(Conformidad.id)
                .join(EntregaItem, EntregaItem.id == Conformidad.entrega_item_id)
                .where(
                    EntregaItem.entrega_id == e.id,
                    Conformidad.resultado == ResultadoConformidad.CON_OBSERVACIONES,
                )
                .limit(1)
            ) is not None

            self.db.add(FactEntrega(
                tiempo_id=_tiempo_id(e.fecha_real) if e.fecha_real else None,
                entrega_id=e.id,
                pedido_id=e.pedido_id,
                tipo=e.tipo.value,
                a_tiempo=a_tiempo,
                con_observaciones=con_obs,
            ))
            inserted += 1
        return inserted


def _tiempo_id(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return dt.year * 10000 + dt.month * 100 + dt.day
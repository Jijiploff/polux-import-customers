"""Pedidos de prueba con múltiples ítems y distintos orígenes.

Ejecutar: `python -m scripts.test_data` (solo si APP_ENV != 'production').
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    Cliente,
    Contrato,
    CategoriaProducto,
    EstadoIngreso,
    EstadoItem,
    EstadoPedido,
    HitoCatalogo,
    ItemHito,
    ModalidadEntrega,
    OrigenItem,
    Pedido,
    PedidoItem,
    Producto,
    SlaHito,
)


def _now() -> datetime:
    return datetime.utcnow()


def _build_items_plan(pedido_items: list[PedidoItem]) -> None:
    """Crea un ItemHito por cada hit del origen del ítem, con fecha_prevista encadenada."""
    pass  # (lo usa `_generate_hitos` abajo)


def _generate_hitos(db, pedido: Pedido, items: list[PedidoItem]) -> None:
    """Crea item_hito para cada ítem, encadenando fecha_prevista con SLA."""
    base = pedido.fecha_ingreso
    for item in items:
        hitos = db.scalars(
            select(HitoCatalogo)
            .where(HitoCatalogo.origen == item.origen, HitoCatalogo.activo== True)
            .order_by(HitoCatalogo.orden)
        ).all()
        prev = base
        for h in hitos:
            sla = db.scalar(
                select(SlaHito).where(SlaHito.hito_id == h.id, SlaHito.origen == item.origen)
            )
            fecha_prevista = prev + timedelta(days=(sla.dias_maximos if sla else 0))
            db.add(ItemHito(
                pedido_item_id=item.id,
                hito_id=h.id,
                fecha_prevista=fecha_prevista,
                estado="PENDIENTE",
            ))
            prev = fecha_prevista


def run() -> None:
    settings = get_settings()
    if settings.APP_ENV.lower() == "production":
        raise SystemExit("test_data no corre en producción.")

    db = SessionLocal()
    try:
        # Clientes
        cliente1 = db.scalar(select(Cliente).filter_by(documento="70000001"))
        if not cliente1:
            cliente1 = Cliente(
                documento="70000001", nombre="María Rodríguez",
                telefono_whatsapp="+51987000001", email="maria@example.com",
                consentimiento_datos=True, consentimiento_fecha=_now(),
            )
            db.add(cliente1)
            db.flush()

        cliente2 = db.scalar(select(Cliente).filter_by(documento="70000002"))
        if not cliente2:
            cliente2 = Cliente(
                documento="70000002", nombre="Carlos Mendoza",
                telefono_whatsapp="+51987000002", email="carlos@example.com",
                consentimiento_datos=True, consentimiento_fecha=_now(),
            )
            db.add(cliente2)
            db.flush()

        # Productos
        productos = {}
        for sku, nombre, cat in [
            ("IPHONE15PM-256-BLK", "iPhone 15 Pro Max 256GB Negro", CategoriaProducto.IPHONE),
            ("IPHONE15-128-BLU", "iPhone 15 128GB Azul", CategoriaProducto.IPHONE),
            ("AIRPODSPRO2", "AirPods Pro 2", CategoriaProducto.AIRPODS),
            ("MACBOOKAIR-M3", "MacBook Air M3 13\"", CategoriaProducto.MACBOOK),
        ]:
            p = db.scalar(select(Producto).filter_by(sku=sku))
            if not p:
                p = Producto(sku=sku, nombre=nombre, categoria=cat, activo=True)
                db.add(p)
                db.flush()
            productos[sku] = p

        # Contratos
        contrato1 = db.scalar(select(Contrato).filter_by(numero="CT-2025-001"))
        if not contrato1:
            contrato1 = Contrato(
                numero="CT-2025-001", cliente_id=cliente1.id,
                fecha_firma=(_now() - timedelta(days=10)).date(),
                monto_total=Decimal("1599.00"), moneda="USD",
            )
            db.add(contrato1)
            db.flush()

        contrato2 = db.scalar(select(Contrato).filter_by(numero="CT-2025-002"))
        if not contrato2:
            contrato2 = Contrato(
                numero="CT-2025-002", cliente_id=cliente2.id,
                fecha_firma=(_now() - timedelta(days=5)).date(),
                monto_total=Decimal("2899.00"), moneda="USD",
            )
            db.add(contrato2)
            db.flush()

        # ---- Pedido 1: 1 ítem stock, en tiempo ----
        if not db.scalar(select(Pedido).filter_by(codigo="PD-2025-0001")):
            p1 = Pedido(
                codigo="PD-2025-0001", contrato_id=contrato1.id, cliente_id=cliente1.id,
                estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
                estado_actual=EstadoPedido.EN_PROCESO,
                fecha_ingreso=_now() - timedelta(days=3),
                fecha_prometida=_now() + timedelta(days=4),
                modalidad_entrega=ModalidadEntrega.DOMICILIO,
                direccion_entrega="Av. Larco 123, Trujillo",
                consentimiento_comunicaciones=True,
            )
            db.add(p1)
            db.flush()
            it1 = PedidoItem(
                pedido_id=p1.id, producto_id=productos["AIRPODSPRO2"].id,
                descripcion_producto=productos["AIRPODSPRO2"].nombre,
                modelo="AirPods Pro 2", color="Blanco", capacidad=None,
                cantidad=1, accesorios="Cable USB-C, estuche MagSafe",
                origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.EN_PROCESO,
            )
            db.add(it1)
            db.flush()
            _generate_hitos(db, p1, [it1])

        # ---- Pedido 2: mixto (stock + importación) ----
        if not db.scalar(select(Pedido).filter_by(codigo="PD-2025-0002")):
            p2 = Pedido(
                codigo="PD-2025-0002", contrato_id=contrato1.id, cliente_id=cliente1.id,
                estado_ingreso=EstadoIngreso.PAGO_COMPLETO_VERIFICADO,
                estado_actual=EstadoPedido.EN_PROCESO,
                fecha_ingreso=_now() - timedelta(days=8),
                fecha_prometida=_now() + timedelta(days=25),
                modalidad_entrega=ModalidadEntrega.DOMICILIO,
                direccion_entrega="Av. Larco 123, Trujillo",
                consentimiento_comunicaciones=True,
            )
            db.add(p2)
            db.flush()
            it2a = PedidoItem(
                pedido_id=p2.id, producto_id=productos["IPHONE15PM-256-BLK"].id,
                descripcion_producto=productos["IPHONE15PM-256-BLK"].nombre,
                modelo="iPhone 15 Pro Max", color="Negro Titanio", capacidad="256GB",
                cantidad=1, accesorios="Cable USB-C",
                origen=OrigenItem.IMPORTACION, estado=EstadoItem.EN_PROCESO,
            )
            it2b = PedidoItem(
                pedido_id=p2.id, producto_id=productos["AIRPODSPRO2"].id,
                descripcion_producto=productos["AIRPODSPRO2"].nombre,
                modelo="AirPods Pro 2", color="Blanco", capacidad=None,
                cantidad=1, accesorios="Cable USB-C, estuche MagSafe",
                origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.EN_PROCESO,
            )
            db.add_all([it2a, it2b])
            db.flush()
            _generate_hitos(db, p2, [it2a, it2b])

        # ---- Pedido 3: multi-ítem, todo importación ----
        if not db.scalar(select(Pedido).filter_by(codigo="PD-2025-0003")):
            p3 = Pedido(
                codigo="PD-2025-0003", contrato_id=contrato2.id, cliente_id=cliente2.id,
                estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
                estado_actual=EstadoPedido.EN_PROCESO,
                fecha_ingreso=_now() - timedelta(days=15),
                fecha_prometida=_now() + timedelta(days=20),
                modalidad_entrega=ModalidadEntrega.RECOJO,
                consentimiento_comunicaciones=True,
            )
            db.add(p3)
            db.flush()
            it3a = PedidoItem(
                pedido_id=p3.id, producto_id=productos["MACBOOKAIR-M3"].id,
                descripcion_producto=productos["MACBOOKAIR-M3"].nombre,
                modelo="MacBook Air M3 13\"", color="Medianoche", capacidad="512GB",
                cantidad=1, accesorios="Cargador 35W, cable USB-C",
                origen=OrigenItem.IMPORTACION, estado=EstadoItem.EN_PROCESO,
            )
            it3b = PedidoItem(
                pedido_id=p3.id, producto_id=productos["IPHONE15-128-BLU"].id,
                descripcion_producto=productos["IPHONE15-128-BLU"].nombre,
                modelo="iPhone 15", color="Azul", capacidad="128GB",
                cantidad=2, accesorios="Cable USB-C",
                origen=OrigenItem.IMPORTACION, estado=EstadoItem.EN_PROCESO,
            )
            db.add_all([it3a, it3b])
            db.flush()
            _generate_hitos(db, p3, [it3a, it3b])

        db.commit()
        print("[test_data] OK — 3 pedidos, 5 ítems, hitos generados.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
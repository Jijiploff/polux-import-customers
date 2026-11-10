"""Verifica que el ETL puebla TODOS los hechos del modelo dimensional."""
from datetime import datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    Cliente, Comunicacion, Conformidad, DireccionComunicacion, Entrega, EntregaItem,
    EstadoEntrega, EstadoImprevisto, EstadoIngreso, EstadoItem, EstadoPedido,
    FactComunicacion, FactEntrega, FactEscalamiento, FactHitoPedido, FactImprevisto,
    Imprevisto, ItemHito, ModalidadEntrega, OrigenItem, Pedido, PedidoItem,
    ResultadoConformidad, TipoEntrega, TipoImprevisto,
)
from app.services.fact_sync_service import FactSyncService


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_pedido(db):
    suf = uuid.uuid4().hex[:6]
    cli = Cliente(nombre=f"C{suf}", consentimiento_datos=True,
                  consentimiento_fecha=datetime.utcnow())
    db.add(cli); db.flush()
    ped = Pedido(
        codigo=f"PD-FS-{suf}", cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow() - timedelta(days=3),
        fecha_prometida=datetime.utcnow() + timedelta(days=3),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped); db.flush()
    item = PedidoItem(pedido_id=ped.id, descripcion_producto="Test", cantidad=1,
                      origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.EN_PROCESO)
    db.add(item); db.flush()
    db.commit()
    db.refresh(ped); db.refresh(item)
    return ped, item


def _cleanup(db, pedido_id):
    from tests.db_utils import cleanup_pedido
    cleanup_pedido(db, pedido_id)


def test_fact_comunicacion(db):
    ped, _ = _mk_pedido(db)
    try:
        db.add(Comunicacion(
            pedido_id=ped.id, direccion=DireccionComunicacion.ENTRANTE,
            canal="WHATSAPP", contenido="Hola", autor="CLIENTE",
            escalado=False, fecha=datetime.utcnow(),
        ))
        db.commit()
        counts = FactSyncService(db).sync_all()
        assert counts["fact_comunicacion"] >= 1
        assert db.scalar(select(FactComunicacion).where(
            FactComunicacion.pedido_id == ped.id
        )) is not None
    finally:
        _cleanup(db, ped.id)


def test_fact_imprevisto(db):
    ped, _ = _mk_pedido(db)
    try:
        db.add(Imprevisto(
            pedido_id=ped.id, tipo=TipoImprevisto.ADUANERO,
            descripcion="Retención", fecha_deteccion=datetime.utcnow() - timedelta(days=2),
            fecha_resolucion=datetime.utcnow(),
            estado=EstadoImprevisto.RESUELTO,
        ))
        db.commit()
        FactSyncService(db).sync_all()
        f = db.scalar(select(FactImprevisto).where(FactImprevisto.pedido_id == ped.id))
        assert f is not None
        assert f.dias_resolucion is not None
        assert f.dias_resolucion >= 1.9  # ~2 días
    finally:
        _cleanup(db, ped.id)


def test_fact_entrega_completa(db):
    ped, item = _mk_pedido(db)
    try:
        e = Entrega(
            pedido_id=ped.id, tipo=TipoEntrega.COMPLETA,
            modalidad=ModalidadEntrega.DOMICILIO,
            fecha_programada=datetime.utcnow() - timedelta(days=1),
            fecha_real=datetime.utcnow(),
            estado=EstadoEntrega.ENTREGADA,
        )
        db.add(e); db.flush()
        ei = EntregaItem(entrega_id=e.id, pedido_item_id=item.id)
        db.add(ei); db.flush()
        db.add(Conformidad(
            entrega_item_id=ei.id,
            checklist_caja_sellada=True, checklist_modelo_ok=True,
            checklist_color_ok=True, checklist_capacidad_ok=True,
            checklist_imei_ok=True, checklist_accesorios_ok=True,
            resultado=ResultadoConformidad.CONFORME,
            fecha_registro=datetime.utcnow(),
        ))
        db.commit()
        FactSyncService(db).sync_all()
        f = db.scalar(select(FactEntrega).where(FactEntrega.pedido_id == ped.id))
        assert f is not None
        assert f.tipo == "COMPLETA"
        assert f.con_observaciones is False
        # fecha_real (hoy) <= fecha_prometida (hoy+3) → a tiempo
        assert f.a_tiempo is True
    finally:
        _cleanup(db, ped.id)


def test_fact_hito_notificado_no_oportuno(db):
    from app.models import HitoCatalogo
    ped, item = _mk_pedido(db)
    try:
        hito = db.scalar(select(HitoCatalogo).where(
            HitoCatalogo.codigo == "STOCK_PREPARACION"
        ))
        if hito is None:
            hito = HitoCatalogo(codigo="STOCK_PREPARACION", nombre="Preparación",
                                origen=OrigenItem.STOCK_TRUJILLO, orden=1, activo=True)
            db.add(hito); db.flush()
        now = datetime.utcnow()
        ih = ItemHito(
            pedido_item_id=item.id, hito_id=hito.id,
            fecha_prevista=now - timedelta(days=2),
            fecha_real=now - timedelta(days=2),
            fecha_notificacion=now,  # 48h después → no oportuno
            estado="COMPLETADO",
            notificado_cliente=True,
        )
        db.add(ih); db.commit()
        FactSyncService(db).sync_all()
        f = db.scalar(select(FactHitoPedido).where(FactHitoPedido.item_hito_id == ih.id))
        assert f is not None
        assert f.notificado_oportuno is False
    finally:
        _cleanup(db, ped.id)
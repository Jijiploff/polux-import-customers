"""Pruebas de serie temporal y validación de KPIs (Fase 7)."""
from datetime import date, datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    Cliente, Comunicacion, DireccionComunicacion, Entrega, EntregaItem,
    EstadoEntrega, EstadoIngreso, EstadoItem, EstadoPedido, HitoCatalogo,
    ItemHito, ModalidadEntrega, OrigenItem, Pedido, PedidoItem, TipoEntrega,
    Conformidad, ResultadoConformidad,
)
from app.services.fact_sync_service import FactSyncService
from tests.db_utils import cleanup_pedido


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_pedido_con_hito_completado(db, *, dias_atraso=0, notificado=True):
    suf = uuid.uuid4().hex[:6]
    cli = Cliente(nombre=f"C{suf}", consentimiento_datos=True)
    db.add(cli); db.flush()
    ped = Pedido(
        codigo=f"PD-KPI-{suf}", cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        # Las columnas de pedido/item_hito son DateTime (no Date)
        fecha_ingreso=datetime.utcnow() - timedelta(days=5),
        fecha_prometida=datetime.utcnow() + timedelta(days=5),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped); db.flush()
    item = PedidoItem(pedido_id=ped.id, descripcion_producto="Test",
                      cantidad=1, origen=OrigenItem.STOCK_TRUJILLO,
                      estado=EstadoItem.EN_PROCESO)
    db.add(item); db.flush()
    hito = db.scalar(select(HitoCatalogo).where(HitoCatalogo.codigo == "STOCK_PREPARACION"))
    if not hito:
        hito = HitoCatalogo(codigo="STOCK_PREPARACION", nombre="Preparación",
                            origen=OrigenItem.STOCK_TRUJILLO, orden=1, activo=True)
        db.add(hito); db.flush()
    ih = ItemHito(
        pedido_item_id=item.id, hito_id=hito.id,
        fecha_prevista=datetime.utcnow() - timedelta(days=3),
        fecha_real=datetime.utcnow() - timedelta(days=2),
        estado="COMPLETADO",
        dias_atraso=dias_atraso,
        notificado_cliente=notificado,
        fecha_notificacion=(datetime.utcnow() - timedelta(days=2)) if notificado else None,
    )
    db.add(ih)
    db.commit()
    db.refresh(ped)
    return ped, item, ih


def _cleanup(db, pedido_id):
    cleanup_pedido(db, pedido_id)


def test_fact_sync_puebla_fact_hito(db):
    ped, item, ih = _mk_pedido_con_hito_completado(db)
    try:
        counts = FactSyncService(db).sync_all()
        assert counts["fact_hito_pedido"] >= 1
        from app.models import FactHitoPedido
        f = db.scalar(select(FactHitoPedido).where(FactHitoPedido.item_hito_id == ih.id))
        assert f is not None
        assert f.completado is True
        assert f.notificado_oportuno is True  # notificado el mismo día
        assert f.origen == "STOCK_TRUJILLO"
    finally:
        _cleanup(db, ped.id)


def test_fact_sync_es_idempotente(db):
    ped, item, ih = _mk_pedido_con_hito_completado(db)
    try:
        FactSyncService(db).sync_all()
        counts2 = FactSyncService(db).sync_all()
        assert counts2["fact_hito_pedido"] == 0  # no vuelve a insertar
    finally:
        _cleanup(db, ped.id)


def test_serie_kpi_actualizacion(client, auth):
    r = client.get(
        "/api/v1/kpis/FREQ_ACTUALIZACION_CLIENTE/serie",
        headers=auth["gerente"],
        params={
            "desde": (date.today() - timedelta(days=30)).isoformat(),
            "hasta": date.today().isoformat(),
            "granularidad": "mes",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["granularidad"] == "mes"
    assert isinstance(body["serie"], list)


def test_serie_kpi_invalido(client, auth):
    r = client.get(
        "/api/v1/kpis/NO_EXISTE/serie",
        headers=auth["gerente"],
        params={
            "desde": "2025-01-01", "hasta": "2025-12-31", "granularidad": "mes",
        },
    )
    assert r.status_code == 400


def test_serie_desde_mayor_hasta(client, auth):
    r = client.get(
        "/api/v1/kpis/ENTREGAS_A_TIEMPO/serie",
        headers=auth["gerente"],
        params={"desde": "2025-12-31", "hasta": "2025-01-01", "granularidad": "mes"},
    )
    assert r.status_code == 400


def test_filtros_opciones(client, auth):
    r = client.get("/api/v1/kpis/filtros/opciones", headers=auth["gerente"])
    assert r.status_code == 200
    data = r.json()
    assert "productos" in data
    assert "origenes" in data
    assert len(data["origenes"]) == 2


def test_validacion_devuelve_sql(client, auth):
    r = client.get("/api/v1/kpis/validacion", headers=auth["gerente"])
    assert r.status_code == 200
    data = r.json()
    # Los 7 KPIs deben tener SQL reproducible
    for codigo in [
        "FREQ_ACTUALIZACION_CLIENTE", "TASA_RESOLUCION_AUTOMATICA",
        "TIEMPO_RESPUESTA_ESCALADOS", "TIEMPO_RESOLUCION_IMPREVISTOS",
        "ENTREGAS_A_TIEMPO", "ENTREGAS_SIN_OBSERVACIONES", "PCT_ENTREGAS_PARCIALES",
    ]:
        assert codigo in data
        assert "sql" in data[codigo]
        assert data[codigo]["sql"].strip().upper().startswith(("SELECT", "WITH"))


def test_admin_sync_facts(client, auth):
    r = client.post("/api/v1/admin/sync-facts", headers=auth["admin"])
    assert r.status_code == 200
    assert "counts" in r.json()


def test_operador_no_puede_sync_facts(client, auth):
    r = client.post("/api/v1/admin/sync-facts", headers=auth["operador"])
    assert r.status_code == 403
"""Pruebas de regresión para los 4 bugs críticos corregidos en esta fase."""
from datetime import datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    Cliente, EstadoHito, EstadoIngreso, EstadoItem, EstadoPedido, HitoCatalogo,
    ItemHito, ModalidadEntrega, OrigenItem, Pedido, PedidoItem, SlaHito,
)
from app.services.pedido_service import get_pedido
from app.services.rule_engine import RuleEngine
from tests.db_utils import cleanup_pedido, crear_pedido_listo


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk(db):
    suf = uuid.uuid4().hex[:6]
    cli = Cliente(nombre=f"C{suf}", consentimiento_datos=True)
    db.add(cli); db.flush()
    ped = Pedido(
        codigo=f"PD-FX-{suf}", cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow() + timedelta(days=7),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped); db.flush()
    item = PedidoItem(
        pedido_id=ped.id, descripcion_producto="X", cantidad=1,
        origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.EN_PROCESO,
    )
    db.add(item); db.flush()
    hito = db.scalar(select(HitoCatalogo).where(HitoCatalogo.codigo == "STOCK_PREPARACION"))
    if hito is None:
        hito = HitoCatalogo(codigo="STOCK_PREPARACION", nombre="Preparación",
                            origen=OrigenItem.STOCK_TRUJILLO, orden=1, activo=True)
        db.add(hito); db.flush()
        db.add(SlaHito(hito_id=hito.id, origen=OrigenItem.STOCK_TRUJILLO,
                       dias_maximos=1, activo=True))
    ih = ItemHito(
        pedido_item_id=item.id, hito_id=hito.id,
        fecha_prevista=datetime.utcnow() - timedelta(days=3),
        estado=EstadoHito.PENDIENTE,
        dias_atraso=0,
    )
    db.add(ih); db.commit()
    db.refresh(ped); db.refresh(item); db.refresh(ih)
    return ped, item, ih


def _cleanup(db, pedido_id):
    from tests.db_utils import cleanup_pedido
    cleanup_pedido(db, pedido_id)


def test_run_all_detecta_atrasos(db):
    """Bug #1: sin la llamada a registrar_atrasos, el hito nunca pasa a ATRASADO."""
    _, _, ih = _mk(db)
    try:
        RuleEngine(db).run_all()
        db.refresh(ih)
        assert ih.estado == EstadoHito.ATRASADO
        assert ih.dias_atraso >= 2
    finally:
        _cleanup(db, ih.item.pedido_id)


def test_get_pedido_carga_hito_para_serializer(db):
    """Bug #2/#3: get_pedido debe cargar ItemHito.hito para que ItemHitoRead
    rellene hito_codigo / hito_nombre."""
    ped, item, _ = _mk(db)
    try:
        loaded = get_pedido(db, ped.id)
        assert loaded is not None
        from app.schemas.pedido import PedidoFullDetail
        schema = PedidoFullDetail.model_validate(loaded)
        hito_out = schema.items[0].hitos[0]
        assert hito_out.hito_codigo == "STOCK_PREPARACION"
        assert hito_out.hito_nombre == "Preparación"
    finally:
        _cleanup(db, ped.id)


def test_no_se_puede_cerrar_caso_sin_primera_accion(client, auth):
    """Regla de negocio: cierre de caso exige primera acción humana registrada."""
    # Pedido de prueba propio (no ensuciar ni depender de los pedidos demo)
    db = SessionLocal()
    try:
        ped, _, _ = crear_pedido_listo(db)
        pid = ped.id
    finally:
        db.close()
    try:
        caso = client.post(
            "/api/v1/casos",
            headers=auth["operador"],
            json={"pedido_id": pid, "motivo": "RECLAMO",
                  "descripcion": "test cierre", "prioridad": "ALTA"},
        )
        assert caso.status_code == 200
        cid = caso.json()["id"]

        r_cierre = client.patch(
            f"/api/v1/casos/{cid}",
            headers=auth["operador"],
            json={"estado": "CERRADO"},
        )
        assert r_cierre.status_code == 409
        assert "primera acción" in r_cierre.json()["detail"]

        # Con primera acción sí se puede cerrar
        client.patch(f"/api/v1/casos/{cid}", headers=auth["operador"],
                     json={"registrar_primera_accion": True})
        r2 = client.patch(f"/api/v1/casos/{cid}", headers=auth["operador"],
                          json={"estado": "CERRADO"})
        assert r2.status_code == 200
        assert r2.json()["estado"] == "CERRADO"
    finally:
        db = SessionLocal()
        try:
            cleanup_pedido(db, pid)
        finally:
            db.close()


def test_entrega_parcial_por_otro_usuario_requiere_admin(client, auth):
    """Bug #4: operador no puede autorizar en nombre de un tercero."""
    # Pedido de prueba propio, ítem ya LISTO_PARA_ENTREGA
    db = SessionLocal()
    try:
        ped, item, _ = crear_pedido_listo(db)
        pid, item_id = ped.id, item.id
    finally:
        db.close()
    try:
        r_bad = client.post(
            "/api/v1/entregas",
            headers=auth["operador"],
            json={
                "pedido_id": pid, "tipo": "PARCIAL", "modalidad": "DOMICILIO",
                "fecha_programada": datetime.utcnow().isoformat(),
                "pedido_item_ids": [item_id],
                "autorizada_por_id": 99999,   # usuario distinto
                "fecha_autorizacion": datetime.utcnow().isoformat(),
                "motivo_parcial": "excepción",
            },
        )
        assert r_bad.status_code in (400, 403)
    finally:
        db = SessionLocal()
        try:
            cleanup_pedido(db, pid)
        finally:
            db.close()
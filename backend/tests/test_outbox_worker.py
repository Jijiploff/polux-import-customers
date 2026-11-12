"""Pruebas del outbox worker: envío, reintentos y fallback a email."""
from datetime import datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    Cliente, Comunicacion, EstadoIngreso, EstadoItem, EstadoPedido,
    ModalidadEntrega, OrigenItem, Pedido, PedidoItem, PlantillaMensaje,
)
from app.services.outbox_worker import OutboxWorker


@pytest.fixture(autouse=True)
def _force_dry_run(monkeypatch):
    monkeypatch.setenv("WHATSAPP_DRY_RUN", "true")
    monkeypatch.setenv("WHATSAPP_ENABLED", "true")
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    get_settings.cache_clear()


def _mk(db, *, phone="+51987000999", email="x@y.com"):
    suf = uuid.uuid4().hex[:6]
    cli = Cliente(nombre=f"C{suf}", telefono_whatsapp=phone, email=email,
                  consentimiento_datos=True, consentimiento_fecha=datetime.utcnow())
    db.add(cli); db.flush()
    ped = Pedido(
        codigo=f"PD-OUT-{suf}", cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow(), fecha_prometida=datetime.utcnow(),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped); db.flush()
    db.add(PedidoItem(pedido_id=ped.id, descripcion_producto="X", cantidad=1,
                      origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.EN_PROCESO))
    db.commit(); db.refresh(ped)
    return ped


def _mk_com(db, pedido_id, *, canal="WHATSAPP", estado="PENDING"):
    com = Comunicacion(
        pedido_id=pedido_id, direccion="SALIENTE", canal=canal,
        contenido="Hola test", autor="AGENTE", estado_entrega=estado,
        fecha=datetime.utcnow(),
    )
    db.add(com); db.commit(); db.refresh(com)
    return com


def _cleanup(db, pedido_id):
    from tests.db_utils import cleanup_pedido
    cleanup_pedido(db, pedido_id)


def test_outbox_envia_pendiente():
    db = SessionLocal()
    try:
        ped = _mk(db)
        com = _mk_com(db, ped.id)
        counts = OutboxWorker(db).process_batch(batch_size=10)
        assert counts["sent"] >= 1
        db.refresh(com)
        assert com.estado_entrega == "SENT"
        assert com.whatsapp_message_id.startswith("dryrun.")
    finally:
        _cleanup(db, ped.id); db.close()


def test_outbox_claim_is_single_use():
    db = SessionLocal()
    try:
        ped = _mk(db)
        com = _mk_com(db, ped.id)
        worker = OutboxWorker(db)

        assert worker._claim_communication(com.id) is True
        assert worker._claim_communication(com.id) is False

        db.refresh(com)
        assert com.estado_entrega == "SENDING"
    finally:
        _cleanup(db, ped.id); db.close()


def test_outbox_respeta_proximo_intento_futuro():
    db = SessionLocal()
    try:
        ped = _mk(db)
        com = _mk_com(db, ped.id, estado="FAILED_RETRY")
        com.proximo_intento = datetime.utcnow() + timedelta(hours=1)
        db.commit()
        counts = OutboxWorker(db).process_batch(batch_size=10)
        # No debe procesarse todavía
        db.refresh(com)
        assert com.estado_entrega == "FAILED_RETRY"
    finally:
        _cleanup(db, ped.id); db.close()


def test_outbox_email_directo():
    db = SessionLocal()
    try:
        ped = _mk(db)
        com = _mk_com(db, ped.id, canal="EMAIL")
        counts = OutboxWorker(db).process_batch(batch_size=10)
        assert counts["sent"] >= 1
        db.refresh(com)
        assert com.estado_entrega == "SENT_EMAIL"
    finally:
        _cleanup(db, ped.id); db.close()


def test_outbox_endpoint_admin(client, auth):
    r = client.post("/api/v1/outbox/run", headers=auth["admin"])
    assert r.status_code == 200
    assert "counts" in r.json()


def test_outbox_endpoint_operador_denegado(client, auth):
    r = client.post("/api/v1/outbox/run", headers=auth["operador"])
    assert r.status_code == 403
"""Pruebas de webhooks de WhatsApp: verificación, firma y deduplicación."""
import hashlib
import hmac
import json
from datetime import datetime
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    Cliente, Comunicacion, EstadoIngreso, EstadoItem, EstadoPedido,
    ModalidadEntrega, OrigenItem, Pedido, PedidoItem,
)


@pytest.fixture(autouse=True)
def _force_dry_run(monkeypatch):
    """Fuerza modo dry-run y un app secret conocido para tests."""
    monkeypatch.setenv("WHATSAPP_DRY_RUN", "true")
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-secret")
    get_settings.cache_clear()


def _sign(body: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _mk_pedido(db, phone: str = "+51987000123") -> Pedido:
    suf = uuid.uuid4().hex[:6]
    cli = Cliente(
        nombre="Cliente WA", telefono_whatsapp=phone, email=f"wa{suf}@x.com",
        consentimiento_datos=True, consentimiento_fecha=datetime.utcnow(),
    )
    db.add(cli)
    db.flush()
    ped = Pedido(
        codigo=f"PD-WA-{suf}", cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow(),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped)
    db.flush()
    db.add(PedidoItem(
        pedido_id=ped.id, descripcion_producto="iPhone", cantidad=1,
        origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.EN_PROCESO,
    ))
    db.commit()
    db.refresh(ped)
    return ped


def _cleanup(db, pedido_id):
    from tests.db_utils import cleanup_pedido
    cleanup_pedido(db, pedido_id)


def test_verification_ok(client):
    r = client.get(
        "/api/v1/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "polux-verify-token",
                "hub.challenge": "12345"},
    )
    assert r.status_code == 200
    assert r.text == "12345"


def test_verification_invalid_token(client):
    r = client.get(
        "/api/v1/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.verify_token": "wrong",
                "hub.challenge": "12345"},
    )
    assert r.status_code == 403


def test_post_invalid_signature_rechaza(client):
    body = json.dumps({"entry": []}).encode()
    r = client.post(
        "/api/v1/webhooks/whatsapp", content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef",
                 "Content-Type": "application/json"},
    )
    assert r.status_code == 401


def test_post_mensaje_entrante_procesado(client):
    db = SessionLocal()
    try:
        ped = _mk_pedido(db, phone="+51987000123")
        ped_id = ped.id
        cli_id = ped.cliente_id
    finally:
        db.close()

    wamid = f"wamid.test.{uuid.uuid4().hex}"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "WABA_ID",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"phone_number_id": "PHONE_ID"},
                    "messages": [{
                        "id": wamid, "from": "51987000123",
                        "timestamp": str(int(datetime.utcnow().timestamp())),
                        "type": "text",
                        "text": {"body": "Hola, ¿cómo va mi pedido?"},
                    }],
                },
            }],
        }],
    }
    body = json.dumps(payload).encode()
    r = client.post(
        "/api/v1/webhooks/whatsapp", content=body,
        headers={"X-Hub-Signature-256": _sign(body),
                 "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["processed"] == 1

    # Verificar que se registró la entrada con wamid
    db = SessionLocal()
    try:
        com = db.scalar(select(Comunicacion).where(Comunicacion.whatsapp_message_id == wamid))
        assert com is not None
        assert com.direccion.value == "ENTRANTE"
        assert com.pedido_id == ped_id
    finally:
        _cleanup(db, ped_id)
        db.close()


def test_deduplicacion_mismo_wamid(client):
    db = SessionLocal()
    try:
        ped = _mk_pedido(db, phone="+51987000456")
        ped_id = ped.id
    finally:
        db.close()

    wamid = f"wamid.test.{uuid.uuid4().hex}"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {
            "messages": [{
                "id": wamid, "from": "51987000456",
                "timestamp": str(int(datetime.utcnow().timestamp())),
                "type": "text", "text": {"body": "Hola"},
            }],
        }}]}],
    }
    body = json.dumps(payload).encode()
    h = {"X-Hub-Signature-256": _sign(body), "Content-Type": "application/json"}

    r1 = client.post("/api/v1/webhooks/whatsapp", content=body, headers=h)
    r2 = client.post("/api/v1/webhooks/whatsapp", content=body, headers=h)
    assert r1.json()["processed"] == 1
    assert r2.json()["duplicated"] == 1

    db = SessionLocal()
    try:
        count = db.query(Comunicacion).filter_by(whatsapp_message_id=wamid).count()
        assert count == 1
    finally:
        _cleanup(db, ped_id)
        db.close()


def test_status_update(client):
    db = SessionLocal()
    try:
        ped = _mk_pedido(db)
        ped_id = ped.id
        wamid = f"wamid.out.{uuid.uuid4().hex}"
        com = Comunicacion(
            pedido_id=ped.id, direccion="SALIENTE", canal="WHATSAPP",
            contenido="Hola", autor="AGENTE",
            estado_entrega="SENT", whatsapp_message_id=wamid,
            fecha=datetime.utcnow(),
        )
        db.add(com)
        db.commit()
    finally:
        db.close()

    payload = {
        "entry": [{"changes": [{"value": {
            "statuses": [{"id": wamid, "status": "delivered",
                          "timestamp": str(int(datetime.utcnow().timestamp()))}],
        }}]}],
    }
    body = json.dumps(payload).encode()
    r = client.post(
        "/api/v1/webhooks/whatsapp", content=body,
        headers={"X-Hub-Signature-256": _sign(body),
                 "Content-Type": "application/json"},
    )
    assert r.status_code == 200
    assert r.json()["statuses_updated"] == 1

    db = SessionLocal()
    try:
        com = db.scalar(select(Comunicacion).where(Comunicacion.whatsapp_message_id == wamid))
        assert com.estado_entrega == "DELIVERED"
    finally:
        _cleanup(db, ped_id)
        db.close()
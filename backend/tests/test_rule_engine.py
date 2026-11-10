"""Pruebas del motor de reglas (Fase 3).

Se ejecuta el motor directamente para evitar depender del scheduler.
Los datos se crean y se limpian por test, usando prefijos únicos.
"""
from datetime import datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    Alerta,
    CasoEscalamiento,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    EstadoAlerta,
    EstadoImprevisto,
    EstadoItem,
    EstadoPedido,
    EstadoIngreso,
    Imprevisto,
    ModalidadEntrega,
    MotivoEscalamiento,
    Pedido,
    PedidoItem,
    OrigenItem,
    Sentimiento,
    TipoImprevisto,
)
from app.services.rule_engine import RuleEngine


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _mk_pedido(db, *, suffix: str, consent: bool = True,
               estado: EstadoPedido = EstadoPedido.RECIBIDO) -> Pedido:
    suf = suffix or uuid.uuid4().hex[:6]
    cli = Cliente(
        nombre=f"Cliente {suf}",
        telefono_whatsapp=f"+5199990{suf}",
        email=f"cli{suf}@example.com",
        consentimiento_datos=consent,
        consentimiento_fecha=datetime.utcnow() if consent else None,
    )
    db.add(cli)
    db.flush()
    ped = Pedido(
        codigo=f"PD-TEST-{suf}",
        cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=estado,
        fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow() + timedelta(days=10),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped)
    db.flush()
    item = PedidoItem(
        pedido_id=ped.id,
        descripcion_producto="iPhone de prueba",
        modelo="iPhone 15",
        color="Negro",
        capacidad="128GB",
        cantidad=1,
        origen=OrigenItem.STOCK_TRUJILLO,
        estado=EstadoItem.PENDIENTE,
    )
    db.add(item)
    db.commit()
    db.refresh(ped)
    return ped


def _cleanup(db, pedido_id: int):
    """Borra en orden seguro (FKs circulares) — ver tests/db_utils.py."""
    from tests.db_utils import cleanup_pedido
    cleanup_pedido(db, pedido_id)


def test_rule_engine_runs_smoke(db):
    counts = RuleEngine(db).run_all()
    assert isinstance(counts, dict)


def test_bienvenida_se_envia_una_sola_vez(db):
    suf = uuid.uuid4().hex[:6]
    ped = _mk_pedido(db, suffix=suf)
    try:
        RuleEngine(db).run_all()
        bienvenidas = db.scalars(
            select(Comunicacion).where(
                Comunicacion.pedido_id == ped.id,
                Comunicacion.direccion == DireccionComunicacion.SALIENTE,
            )
        ).all()
        assert len(bienvenidas) >= 1
        # Segunda corrida no debe duplicar
        RuleEngine(db).run_all()
        bienvenidas2 = db.scalars(
            select(Comunicacion).where(
                Comunicacion.pedido_id == ped.id,
                Comunicacion.direccion == DireccionComunicacion.SALIENTE,
            )
        ).all()
        assert len(bienvenidas) == len(bienvenidas2)
    finally:
        _cleanup(db, ped.id)


def test_consentimiento_revocado_bloquea_comunicacion(db):
    suf = uuid.uuid4().hex[:6]
    ped = _mk_pedido(db, suffix=suf, consent=False)
    try:
        RuleEngine(db).run_all()
        salientes = db.scalars(
            select(Comunicacion).where(
                Comunicacion.pedido_id == ped.id,
                Comunicacion.direccion == DireccionComunicacion.SALIENTE,
            )
        ).all()
        assert salientes == []
    finally:
        _cleanup(db, ped.id)


def test_reclamo_escala_sin_resolver(db):
    suf = uuid.uuid4().hex[:6]
    ped = _mk_pedido(db, suffix=suf)
    try:
        com = Comunicacion(
            pedido_id=ped.id,
            direccion=DireccionComunicacion.ENTRANTE,
            canal="WHATSAPP",
            contenido="Estoy molesto, quiero un reembolso YA",
            intencion_detectada="RECLAMO",
            sentimiento=Sentimiento.NEGATIVO,
            autor="CLIENTE",
            escalado=False,
            fecha=datetime.utcnow(),
        )
        db.add(com)
        db.commit()
        db.refresh(com)

        RuleEngine(db).run_all()

        caso = db.scalar(
            select(CasoEscalamiento).where(
                CasoEscalamiento.pedido_id == ped.id,
                CasoEscalamiento.motivo == MotivoEscalamiento.RECLAMO,
            )
        )
        assert caso is not None
        db.refresh(com)
        assert com.escalado is True
        assert com.caso_id == caso.id
    finally:
        _cleanup(db, ped.id)


def test_imprevisto_genera_alerta_y_caso(db):
    suf = uuid.uuid4().hex[:6]
    ped = _mk_pedido(db, suffix=suf)
    try:
        imp = Imprevisto(
            pedido_id=ped.id,
            tipo=TipoImprevisto.ADUANERO,
            descripcion="Retenido en aduana",
            fecha_deteccion=datetime.utcnow(),
            estado=EstadoImprevisto.ABIERTO,
        )
        db.add(imp)
        db.commit()

        RuleEngine(db).run_all()

        alerta = db.scalar(
            select(Alerta).where(
                Alerta.pedido_id == ped.id, Alerta.estado == EstadoAlerta.ABIERTA
            )
        )
        caso = db.scalar(
            select(CasoEscalamiento).where(
                CasoEscalamiento.pedido_id == ped.id,
                CasoEscalamiento.motivo == MotivoEscalamiento.IMPREVISTO,
            )
        )
        assert alerta is not None
        assert caso is not None
    finally:
        _cleanup(db, ped.id)


def test_atender_alerta_endpoint(client, auth):
    # Crea una alerta directamente en BD y la atiende por HTTP.
    db = SessionLocal()
    try:
        suf = uuid.uuid4().hex[:6]
        ped = _mk_pedido(db, suffix=suf)
        alerta = Alerta(
            tipo="RETRASO_LEVE",
            pedido_id=ped.id,
            severidad="MEDIA",
            mensaje="test",
            estado=EstadoAlerta.ABIERTA,
            fecha_deteccion=datetime.utcnow(),
        )
        db.add(alerta)
        db.commit()
        db.refresh(alerta)
        alerta_id = alerta.id
    finally:
        db.close()

    r = client.patch(f"/api/v1/alertas/{alerta_id}/atender", headers=auth["operador"])
    assert r.status_code == 200
    assert r.json()["estado"] == "ATENDIDA"

    # Cleanup
    db = SessionLocal()
    try:
        _cleanup(db, ped.id)
    finally:
        db.close()


def test_admin_run_rules_endpoint(client, auth):
    r = client.post("/api/v1/admin/run-rules", headers=auth["admin"])
    assert r.status_code == 200
    assert "counts" in r.json()


def test_operador_no_puede_ejecutar_run_rules(client, auth):
    r = client.post("/api/v1/admin/run-rules", headers=auth["operador"])
    assert r.status_code == 403
"""Pruebas de respuestas generales e idempotencia de reglas."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    Alerta,
    Cliente,
    Comunicacion,
    EstadoAlerta,
    EstadoImprevisto,
    EstadoIngreso,
    EstadoPedido,
    Imprevisto,
    ModalidadEntrega,
    Pedido,
    TipoImprevisto,
)
from app.services.agent_service import AgentService
from app.services.knowledge_base import respuesta
from app.services.llm_provider import MockProvider
from app.services.rule_engine import RuleEngine
from app.schemas.agent import IncomingMessage
from tests.db_utils import cleanup_pedido


@pytest.fixture
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_base_conocimiento_responde_capacidades():
    assert "estado" in respuesta("¿Qué cosas puedes hacer?").lower()


def test_consulta_general_con_pedido_se_persiste_una_respuesta(db):
    sufijo = uuid.uuid4().hex[:8]
    cliente = Cliente(
        nombre=f"KB {sufijo}",
        consentimiento_datos=True,
        consentimiento_fecha=datetime.utcnow(),
    )
    db.add(cliente)
    db.flush()
    pedido = Pedido(
        codigo=f"PD-KB-{sufijo}",
        cliente_id=cliente.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow() + timedelta(days=4),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(pedido)
    db.commit()
    try:
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=pedido.id, contenido="¿Qué cosas puedes hacer?")
        )
        assert "estado" in result.response_text.lower()
        assert result.outgoing_comunicacion_id is not None
    finally:
        db.execute(delete(Comunicacion).where(Comunicacion.pedido_id == pedido.id))
        db.execute(delete(Alerta).where(Alerta.pedido_id == pedido.id))
        db.execute(delete(Imprevisto).where(Imprevisto.pedido_id == pedido.id))
        cleanup_pedido(db, pedido.id)


def test_alerta_imprevisto_no_se_duplica_en_cinco_ejecuciones(db):
    sufijo = uuid.uuid4().hex[:8]
    cliente = Cliente(
        nombre=f"Alerta {sufijo}", consentimiento_datos=True,
        consentimiento_fecha=datetime.utcnow(),
    )
    db.add(cliente)
    db.flush()
    pedido = Pedido(
        codigo=f"PD-AL-{sufijo}", cliente_id=cliente.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO, fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow() + timedelta(days=4),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(pedido)
    db.flush()
    db.add(Imprevisto(
        pedido_id=pedido.id, tipo=TipoImprevisto.ADUANERO,
        descripcion="Retenido", fecha_deteccion=datetime.utcnow(),
        estado=EstadoImprevisto.ABIERTO,
    ))
    db.commit()
    try:
        for _ in range(5):
            motor = RuleEngine(db)
            motor._rule_imprevisto()
            db.commit()
        alertas = db.scalars(select(Alerta).where(
            Alerta.pedido_id == pedido.id,
            Alerta.tipo == "IMPREVISTO",
            Alerta.estado == EstadoAlerta.ABIERTA,
        )).all()
        comunicaciones = db.scalars(select(Comunicacion).where(
            Comunicacion.pedido_id == pedido.id,
            Comunicacion.dedupe_key == f"rule:IMPREVISTO:{db.scalar(select(Imprevisto.id).where(Imprevisto.pedido_id == pedido.id))}",
        )).all()
        assert len(alertas) == 1
        assert len(comunicaciones) == 1
    finally:
        db.execute(delete(Comunicacion).where(Comunicacion.pedido_id == pedido.id))
        db.execute(delete(Alerta).where(Alerta.pedido_id == pedido.id))
        db.execute(delete(Imprevisto).where(Imprevisto.pedido_id == pedido.id))
        cleanup_pedido(db, pedido.id)

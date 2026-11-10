"""Pruebas del agente IA — clasificación, guardrails y flujo completo."""
from datetime import datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    CasoEscalamiento, Cliente, Comunicacion, DireccionComunicacion,
    EstadoImprevisto, EstadoIngreso, EstadoItem, EstadoPedido, Imprevisto,
    ModalidadEntrega, MotivoEscalamiento, OrigenItem, Pedido, PedidoItem,
    TipoImprevisto,
)
from app.schemas.agent import IncomingMessage
from app.services.agent_service import AgentService
from app.services.llm_provider import (
    ClassificationResult, Intent, LLMProvider, MockProvider, Sentiment,
    TipoMensajeEntrante,
)
from tests.db_utils import cleanup_pedido as _cleanup


@pytest.fixture(autouse=True)
def _reset_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk_pedido(db, *, suffix: str | None = None) -> Pedido:
    suf = suffix or uuid.uuid4().hex[:6]
    cli = Cliente(
        nombre=f"Cliente {suf}",
        telefono_whatsapp=f"+5199990{suf}",
        email=f"cli{suf}@example.com",
        consentimiento_datos=True,
        consentimiento_fecha=datetime.utcnow(),
    )
    db.add(cli); db.flush()
    ped = Pedido(
        codigo=f"PD-AGENT-{suf}",
        cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow() - timedelta(days=2),
        fecha_prometida=datetime.utcnow() + timedelta(days=8),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped); db.flush()
    db.add(PedidoItem(
        pedido_id=ped.id, descripcion_producto="iPhone 15 Pro Max",
        modelo="iPhone 15 Pro Max", color="Negro", capacidad="256GB",
        cantidad=1, origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.EN_PROCESO,
    ))
    db.commit()
    db.refresh(ped)
    return ped


# --------- Clasificación ---------
def test_classify_saludo():
    assert MockProvider().classify("Hola, buenos días").intent == Intent.SALUDO


def test_classify_reclamo():
    c = MockProvider().classify("Esto es una estafa, quiero mi reembolso")
    assert c.intent == Intent.RECLAMO
    assert c.sentiment == Sentiment.NEGATIVO


def test_classify_entrega_parcial():
    assert MockProvider().classify("¿Puedo recibir solo los AirPods primero?").intent \
        == Intent.ENTREGA_PARCIAL


def test_classify_dano():
    c = MockProvider().classify("El iPhone llegó con la pantalla rota")
    assert c.intent == Intent.DAÑO
    assert c.sentiment == Sentiment.NEGATIVO


def test_classify_producto_incorrecto():
    assert MockProvider().classify("No es lo que pedí, me enviaron otro modelo").intent \
        == Intent.PRODUCTO_INCORRECTO


def test_classify_retraso():
    assert MockProvider().classify("¿Por qué no llega? hay mucha demora").intent \
        == Intent.RETRASO


# --------- Flujos ---------
def test_flujo_saludo_usa_plantilla(db):
    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Hola")
        )
        assert result.escalated is False
        out = db.get(Comunicacion, result.outgoing_comunicacion_id)
        assert out.plantilla_id is not None  # usó plantilla AGENTE_SALUDO
    finally:
        _cleanup(db, ped.id)


def test_flujo_dano_escala_critico(db):
    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id,
                            contenido="El iPhone llegó roto, pantalla quebrada")
        )
        assert result.escalated is True
        caso = db.get(CasoEscalamiento, result.caso_id)
        assert caso.prioridad.value == "CRITICA"
    finally:
        _cleanup(db, ped.id)


def test_flujo_producto_incorrecto_escala(db):
    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id,
                            contenido="No es lo que pedí, el color es distinto")
        )
        assert result.escalated is True
    finally:
        _cleanup(db, ped.id)


def test_flujo_pagos_escala_no_solo_redirige(db):
    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="¿Puedo pagar en cuotas?")
        )
        assert result.escalated is True
        assert result.caso_id is not None
        out = db.get(Comunicacion, result.outgoing_comunicacion_id)
        assert out.plantilla_id is not None  # AGENTE_PAGOS_REDIRECT
    finally:
        _cleanup(db, ped.id)


def test_flujo_entrega_parcial_usa_plantilla_holding(db):
    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Quiero recibir solo una parte")
        )
        assert result.escalated is True
        texto = (result.response_text or "").lower()
        for prohibida in ("sí, se puede", "no, no se puede", "autorizada", "aprobada"):
            assert prohibida not in texto
        out = db.get(Comunicacion, result.outgoing_comunicacion_id)
        assert out.plantilla_id is not None
    finally:
        _cleanup(db, ped.id)


def test_evita_duplicado_de_caso(db):
    ped = _mk_pedido(db)
    try:
        svc = AgentService(db, provider=MockProvider())
        r1 = svc.handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Esto es una estafa")
        )
        r2 = svc.handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Quiero mi dinero, pésimo")
        )
        assert r1.caso_id == r2.caso_id  # reutilizó el caso abierto
    finally:
        _cleanup(db, ped.id)


def test_no_responde_si_humano_respondio_reciente(db):
    ped = _mk_pedido(db)
    try:
        # Simula respuesta humana reciente
        db.add(Comunicacion(
            pedido_id=ped.id, direccion=DireccionComunicacion.SALIENTE,
            canal="WHATSAPP", contenido="Hola, ya te ayudo",
            autor="HUMANO", escalado=False, fecha=datetime.utcnow(),
        ))
        db.commit()

        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Hola")
        )
        assert result.human_in_progress is True
        assert result.outgoing_comunicacion_id is None
    finally:
        _cleanup(db, ped.id)


def test_baja_confianza_escala(db):
    class LowConfProvider(LLMProvider):
        name = "low"
        def classify(self, message, context=None):
            return ClassificationResult(
                intent=Intent.ESTADO_PEDIDO, sentiment=Sentiment.NEUTRO,
                confidence=0.10, provider_used="low",
            )
        def compose_response(self, intent, facts):
            return "?"

    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=LowConfProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Duda")
        )
        assert result.escalated is True
        caso = db.get(CasoEscalamiento, result.caso_id)
        assert "confianza" in caso.descripcion.lower()
    finally:
        _cleanup(db, ped.id)


def test_multimedia_escala(db):
    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="[image]",
                            tipo_mensaje=TipoMensajeEntrante.MULTIMEDIA)
        )
        assert result.escalated is True
        assert result.classification.intent == "MULTIMEDIA"
        assert result.caso_id is not None
    finally:
        _cleanup(db, ped.id)


def test_estado_pedido_menciona_imprevisto_activo(db):
    ped = _mk_pedido(db)
    try:
        db.add(Imprevisto(
            pedido_id=ped.id, tipo=TipoImprevisto.ADUANERO,
            descripcion="Retenido", fecha_deteccion=datetime.utcnow(),
            estado=EstadoImprevisto.ABIERTO,
        ))
        db.commit()
        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="¿Cómo va mi pedido?")
        )
        assert "imprevisto" in (result.response_text or "").lower()
    finally:
        _cleanup(db, ped.id)


def test_guardrail_fecha_inventada(db):
    class InventDate(LLMProvider):
        name = "inv"
        def classify(self, message, context=None):
            return ClassificationResult(
                intent=Intent.ESTADO_PEDIDO, sentiment=Sentiment.NEUTRO,
                confidence=0.99, provider_used="inv",
            )
        def compose_response(self, intent, facts):
            return "Tu pedido llega el 31/12/2099 sin falta."

    ped = _mk_pedido(db)
    try:
        result = AgentService(db, provider=InventDate()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="¿Cuándo llega?")
        )
        assert "31/12/2099" not in (result.response_text or "")
        assert result.fallback_used is True
        assert ped.fecha_prometida.strftime("%d/%m/%Y") in (result.response_text or "")
    finally:
        _cleanup(db, ped.id)


def test_guardrail_pii_no_expone_telefono(db):
    class PIIProvider(LLMProvider):
        name = "pii"
        def classify(self, message, context=None):
            return ClassificationResult(
                intent=Intent.ESTADO_PEDIDO, sentiment=Sentiment.NEUTRO,
                confidence=0.99, provider_used="pii",
            )
        def compose_response(self, intent, facts):
            return f"Hola, tu número es +5199990123abc y tu pedido va bien."

    ped = _mk_pedido(db, suffix="000123")
    try:
        result = AgentService(db, provider=PIIProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Hola")
        )
        assert "+5199990123abc" not in (result.response_text or "")
        assert result.fallback_used is True
    finally:
        _cleanup(db, ped.id)


def test_metrics_endpoint(client, auth):
    r = client.get("/api/v1/agent/metrics", headers=auth["operador"])
    assert r.status_code == 200
    body = r.json()
    assert "total_entrantes" in body
    assert "por_intent" in body


def test_test_classify_endpoint_admin(client, auth):
    r = client.post(
        "/api/v1/agent/test/classify",
        headers=auth["admin"],
        json={"contenido": "Esto es una estafa"},
    )
    assert r.status_code == 200
    assert r.json()["intent"] == "RECLAMO"


def test_test_classify_endpoint_operador_denegado(client, auth):
    r = client.post(
        "/api/v1/agent/test/classify",
        headers=auth["operador"],
        json={"contenido": "Hola"},
    )
    assert r.status_code == 403


# --------- Simulador de chat WhatsApp (Fase G2) ---------
def test_chats_y_thread_del_simulador(client, auth, db):
    ped = _mk_pedido(db, suffix="sim1")
    try:
        # Mensaje de cliente por la API (la suite corre con motor local/mock)
        r = client.post(
            "/api/v1/agent/messages/incoming",
            headers=auth["operador"],
            json={"pedido_id": ped.id, "canal": "WHATSAPP", "contenido": "Hola"},
        )
        assert r.status_code == 200

        # La bandeja muestra el chat con cliente, preview y conteo
        r = client.get("/api/v1/agent/chats", headers=auth["operador"])
        assert r.status_code == 200
        chat = next((c for c in r.json() if c["pedido_id"] == ped.id), None)
        assert chat is not None
        assert chat["codigo"] == ped.codigo
        assert chat["cliente_nombre"] == ped.cliente.nombre
        assert chat["total_mensajes"] >= 2          # entrante + respuesta
        assert chat["ultima_preview"]
        assert chat["asesor_reciente"] is False

        # El hilo devuelve los mensajes en orden cronológico
        r = client.get(
            f"/api/v1/agent/thread?pedido_id={ped.id}", headers=auth["operador"]
        )
        assert r.status_code == 200
        hilo = r.json()
        assert hilo[0]["autor"] == "CLIENTE"
        assert hilo[-1]["autor"] == "AGENTE"
        assert [m["id"] for m in hilo] == sorted(m["id"] for m in hilo)
    finally:
        _cleanup(db, ped.id)


def test_thread_pedido_inexistente_devuelve_404(client, auth):
    r = client.get("/api/v1/agent/thread?pedido_id=99999999", headers=auth["operador"])
    assert r.status_code == 404


def test_flujo_completo_agente_escala_y_humano_responde(client, auth, db):
    """Cliente reclama → agente clasifica y escala → asesor responde →
    el caso pasa a EN_PROCESO y el agente cede el paso a la persona."""
    ped = _mk_pedido(db, suffix="sim2")
    try:
        # 1) Reclamo: el agente lo detecta, escala y abre caso
        r = client.post(
            "/api/v1/agent/messages/incoming",
            headers=auth["operador"],
            json={"pedido_id": ped.id,
                  "contenido": "Esto es una estafa, quiero mi dinero"},
        )
        assert r.status_code == 200
        res = r.json()
        assert res["escalated"] is True
        assert res["classification"]["intent"] == "RECLAMO"
        caso_id = res["caso_id"]
        assert caso_id

        # 2) El asesor responde desde la plataforma
        r = client.post(
            "/api/v1/agent/human-reply",
            headers=auth["operador"],
            json={"pedido_id": ped.id,
                  "contenido": "Hola, ya estamos revisando tu caso."},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["message"]["autor"] == "HUMANO"
        assert body["message"]["estado_entrega"] == "SENT"
        assert body["caso_id"] == caso_id
        assert body["caso_estado"] == "EN_PROCESO"
        assert body["aviso"]

        # 3) El agente cede el paso: no responde mientras la persona esté activa
        r = client.post(
            "/api/v1/agent/messages/incoming",
            headers=auth["operador"],
            json={"pedido_id": ped.id, "contenido": "gracias"},
        )
        assert r.status_code == 200
        assert r.json()["human_in_progress"] is True

        # 4) El hilo muestra a los tres participantes con trazabilidad del caso
        hilo = client.get(
            f"/api/v1/agent/thread?pedido_id={ped.id}", headers=auth["operador"]
        ).json()
        assert {"CLIENTE", "AGENTE", "HUMANO"} <= {m["autor"] for m in hilo}
        escalado = next(m for m in hilo if m["escalado"])
        assert escalado["caso_id"] == caso_id
        assert escalado["caso_motivo"] == "RECLAMO"

        # La bandeja refleja que hay asesor reciente y caso en proceso
        chat = next(
            c for c in client.get("/api/v1/agent/chats", headers=auth["operador"]).json()
            if c["pedido_id"] == ped.id
        )
        assert chat["asesor_reciente"] is True
        assert chat["caso_abierto_id"] == caso_id
    finally:
        _cleanup(db, ped.id)


def test_respuesta_humana_denegada_para_gerente(client, auth, db):
    ped = _mk_pedido(db, suffix="sim3")
    try:
        r = client.post(
            "/api/v1/agent/human-reply",
            headers=auth["gerente"],
            json={"pedido_id": ped.id, "contenido": "hola"},
        )
        assert r.status_code == 403
    finally:
        _cleanup(db, ped.id)


def test_respuesta_humana_con_pedido_inexistente(client, auth):
    r = client.post(
        "/api/v1/agent/human-reply",
        headers=auth["operador"],
        json={"pedido_id": 99999999, "contenido": "hola"},
    )
    assert r.status_code == 404
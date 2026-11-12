"""Pruebas del agente IA — clasificación, guardrails y flujo completo."""
from datetime import datetime, timedelta
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    AutorComunicacion, Canal, CasoEscalamiento, ClaseComunicacion, Cliente,
    Comunicacion, DireccionComunicacion, EstadoCaso, EstadoImprevisto,
    EstadoIngreso, EstadoItem, EstadoPedido, Imprevisto, ModalidadEntrega,
    MotivoEscalamiento, OrigenItem, Pedido, PedidoItem, PrioridadCaso,
    TipoImprevisto, Usuario,
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


def _user_id(db, email: str) -> int:
    uid = db.scalar(select(Usuario.id).where(Usuario.email == email))
    assert uid is not None
    return uid


def _mk_caso(db, ped: Pedido, *, estado: EstadoCaso = EstadoCaso.ABIERTO) -> CasoEscalamiento:
    caso = CasoEscalamiento(
        pedido_id=ped.id,
        motivo=MotivoEscalamiento.RECLAMO,
        prioridad=PrioridadCaso.ALTA,
        descripcion="Caso creado por la prueba de respuesta local",
        fecha_apertura=datetime.utcnow(),
        estado=estado,
    )
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


class _FakeTelegram:
    enabled = True
    operator_chat_id = ""

    def __init__(self):
        self.sent: list[tuple[str, str]] = []

    def send_message(self, chat_id, text, **_kwargs):
        self.sent.append((str(chat_id), text))
        return SimpleNamespace(ok=True, message_id=1, error=None, retriable=False)

    def redact(self, text):
        return text


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


def test_agente_retoma_cuando_el_caso_esta_cerrado(db):
    ped = _mk_pedido(db)
    caso = _mk_caso(db, ped, estado=EstadoCaso.CERRADO)
    try:
        # El aviso de cierre queda como mensaje humano reciente, pero al
        # pertenecer a un caso cerrado ya no debe pausar al agente.
        db.add(Comunicacion(
            pedido_id=ped.id, direccion=DireccionComunicacion.SALIENTE,
            canal=Canal.TELEGRAM, contenido="Tu caso fue cerrado.",
            autor=AutorComunicacion.HUMANO, clase=ClaseComunicacion.CLIENTE,
            escalado=True, caso_id=caso.id, fecha=datetime.utcnow(),
        ))
        db.commit()

        result = AgentService(db, provider=MockProvider()).handle_incoming_message(
            IncomingMessage(pedido_id=ped.id, contenido="Hola")
        )
        assert result.human_in_progress is False
        assert result.outgoing_comunicacion_id is not None
    finally:
        _cleanup(db, ped.id)


def test_agente_sigue_pausado_si_el_caso_activo_tiene_respuesta_humana(db):
    ped = _mk_pedido(db)
    caso = _mk_caso(db, ped)
    try:
        db.add(Comunicacion(
            pedido_id=ped.id, direccion=DireccionComunicacion.SALIENTE,
            canal=Canal.TELEGRAM, contenido="Ya estoy revisando tu caso.",
            autor=AutorComunicacion.HUMANO, clase=ClaseComunicacion.CLIENTE,
            escalado=True, caso_id=caso.id, fecha=datetime.utcnow(),
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

        # La bandeja del admin muestra todas las conversaciones.
        r = client.get("/api/v1/agent/chats", headers=auth["admin"])
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
            f"/api/v1/agent/thread?pedido_id={ped.id}", headers=auth["admin"]
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


def test_flujo_completo_agente_escala_y_humano_responde(client, auth, db, monkeypatch):
    """Cliente reclama → agente clasifica y escala → asesor responde →
    el caso pasa a EN_PROCESO y el agente cede el paso a la persona."""
    ped = _mk_pedido(db, suffix="sim2")
    ped.cliente.telegram_chat_id = "990001"
    db.commit()

    class FakeTelegram:
        enabled = True
        operator_chat_id = ""

        def __init__(self):
            self.sent = []

        def send_message(self, chat_id, text, **_kwargs):
            self.sent.append((str(chat_id), text))
            return SimpleNamespace(ok=True, message_id=1, error=None, retriable=False)

        def redact(self, text):
            return text

    telegram = FakeTelegram()
    monkeypatch.setattr(
        "app.services.caso_service.TelegramService", lambda: telegram
    )
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
        assert ("990001", "Hola, ya estamos revisando tu caso.") in telegram.sent

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


# --------- Respuesta local a casos (sin usar Telegram en persona) ---------
def test_caso_detalle_y_respuesta_local_asigna_primer_operador(
    client, auth, db, monkeypatch
):
    ped = _mk_pedido(db, suffix="caso1")
    ped.cliente.telegram_chat_id = "9900101"
    db.commit()
    caso = _mk_caso(db, ped)
    telegram = _FakeTelegram()
    monkeypatch.setattr(
        "app.services.caso_service.TelegramService", lambda: telegram
    )
    try:
        # Ficha del caso: datos para que el operador decida si responder.
        r = client.get(f"/api/v1/casos/{caso.id}", headers=auth["operador"])
        assert r.status_code == 200
        detalle = r.json()
        assert detalle["pedido_codigo"] == ped.codigo
        assert detalle["cliente_nombre"] == ped.cliente.nombre
        assert detalle["cliente_telegram_vinculado"] is True
        assert detalle["puede_responder"] is True
        assert detalle["responsable_nombre"] is None

        # Primer operador: responde y queda como responsable.
        r = client.post(
            f"/api/v1/casos/{caso.id}/responder",
            headers=auth["operador"],
            json={"contenido": "Hola, ya estamos revisando tu caso."},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["enviado"] is True
        assert body["caso_estado"] == "EN_PROCESO"
        assert body["message"]["autor"] == "HUMANO"
        assert body["message"]["clase"] == "CLIENTE"
        assert body["message"]["contenido"] == "Hola, ya estamos revisando tu caso."
        assert ("9900101", "Hola, ya estamos revisando tu caso.") in telegram.sent

        db.refresh(caso)
        operador_id = caso.responsable_id
        assert operador_id is not None
        assert caso.estado == EstadoCaso.EN_PROCESO

        # El admin puede apoyar en un caso asignado, sin robar la asignación.
        r = client.post(
            f"/api/v1/casos/{caso.id}/responder",
            headers=auth["admin"],
            json={"contenido": "Yo también quiero responder."},
        )
        assert r.status_code == 200
        assert r.json()["enviado"] is True
        db.refresh(caso)
        assert caso.responsable_id == operador_id

        # La ficha del admin confirma que puede responder casos ajenos.
        detalle_admin = client.get(
            f"/api/v1/casos/{caso.id}", headers=auth["admin"]
        )
        assert detalle_admin.status_code == 200
        assert detalle_admin.json()["puede_responder"] is True

        # El mismo responsable sí puede seguir conversando.
        r = client.post(
            f"/api/v1/casos/{caso.id}/responder",
            headers=auth["operador"],
            json={"contenido": "En breve te confirmamos."},
        )
        assert r.status_code == 200
        assert r.json()["enviado"] is True
    finally:
        _cleanup(db, ped.id)


def test_primera_accion_asigna_caso_libre_y_respeta_asignado(client, auth, db):
    operador_id = _user_id(db, "t.oper@example.com")
    admin_id = _user_id(db, "t.admin@example.com")
    suf = uuid.uuid4().hex[:5]
    ped_operador = _mk_pedido(db, suffix=f"pa1-{suf}")
    ped_asignado = _mk_pedido(db, suffix=f"pa2-{suf}")
    ped_admin = _mk_pedido(db, suffix=f"pa3-{suf}")
    caso_operador = _mk_caso(db, ped_operador)
    caso_asignado = _mk_caso(db, ped_asignado)
    caso_asignado.responsable_id = operador_id
    caso_admin = _mk_caso(db, ped_admin)
    db.commit()
    try:
        # El operador que registra la primera acción reclama el caso libre.
        r = client.patch(
            f"/api/v1/casos/{caso_operador.id}",
            headers=auth["operador"],
            json={"registrar_primera_accion": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["responsable_id"] == operador_id
        assert body["estado"] == "EN_PROCESO"
        assert body["fecha_primera_accion"] is not None

        # El admin puede apoyar sin quitarle el caso al operador responsable.
        r = client.patch(
            f"/api/v1/casos/{caso_asignado.id}",
            headers=auth["admin"],
            json={"registrar_primera_accion": True},
        )
        assert r.status_code == 200
        assert r.json()["responsable_id"] == operador_id

        # Si el caso está libre, el admin también queda como responsable.
        r = client.patch(
            f"/api/v1/casos/{caso_admin.id}",
            headers=auth["admin"],
            json={"registrar_primera_accion": True},
        )
        assert r.status_code == 200
        assert r.json()["responsable_id"] == admin_id
    finally:
        for ped in (ped_operador, ped_asignado, ped_admin):
            _cleanup(db, ped.id)


def test_respuesta_local_sin_telegram_no_asigna_y_audita(client, auth, db):
    ped = _mk_pedido(db, suffix="caso2")
    caso = _mk_caso(db, ped)
    try:
        r = client.post(
            f"/api/v1/casos/{caso.id}/responder",
            headers=auth["operador"],
            json={"contenido": "Intenté responder pero no hay Telegram."},
        )
        assert r.status_code == 400
        assert "Telegram" in r.json()["detail"]

        db.expire_all()
        caso = db.get(CasoEscalamiento, caso.id)
        assert caso.responsable_id is None
        assert caso.estado == EstadoCaso.ABIERTO

        # La conversación no recibió una respuesta falsa; el intento queda
        # registrado como operativo para auditoría.
        cliente_rows = db.scalars(
            select(Comunicacion).where(
                Comunicacion.pedido_id == ped.id,
                Comunicacion.clase == ClaseComunicacion.CLIENTE,
            )
        ).all()
        assert cliente_rows == []
        operativos = db.scalars(
            select(Comunicacion).where(
                Comunicacion.pedido_id == ped.id,
                Comunicacion.clase == ClaseComunicacion.OPERATIVO,
            )
        ).all()
        assert len(operativos) == 1
        assert operativos[0].estado_entrega == "FAILED"
        assert "sin_telegram" in (operativos[0].error_envio or "")
    finally:
        _cleanup(db, ped.id)


def test_respuesta_local_caso_cerrado_devuelve_409(client, auth, db):
    ped = _mk_pedido(db, suffix="caso3")
    caso = _mk_caso(db, ped, estado=EstadoCaso.CERRADO)
    try:
        r = client.post(
            f"/api/v1/casos/{caso.id}/responder",
            headers=auth["operador"],
            json={"contenido": "Mensaje tardío"},
        )
        assert r.status_code == 409
        assert "cerrado" in r.json()["detail"]
    finally:
        _cleanup(db, ped.id)


def test_respuesta_local_denegada_para_gerente(client, auth, db):
    ped = _mk_pedido(db, suffix="caso4")
    caso = _mk_caso(db, ped)
    try:
        r = client.post(
            f"/api/v1/casos/{caso.id}/responder",
            headers=auth["gerente"],
            json={"contenido": "No debería poder responder"},
        )
        assert r.status_code == 403
    finally:
        _cleanup(db, ped.id)


def test_detalle_caso_inexistente_devuelve_404(client, auth):
    r = client.get("/api/v1/casos/99999999", headers=auth["operador"])
    assert r.status_code == 404


def test_cerrar_caso_avisa_al_cliente_y_no_permite_repetir(
    client, auth, db, monkeypatch
):
    ped = _mk_pedido(db, suffix="caso6")
    ped.cliente.telegram_chat_id = "9900106"
    db.commit()
    caso = _mk_caso(db, ped)
    telegram = _FakeTelegram()
    monkeypatch.setattr(
        "app.services.caso_service.TelegramService", lambda: telegram
    )
    try:
        r = client.post(
            f"/api/v1/casos/{caso.id}/cerrar", headers=auth["operador"]
        )
        assert r.status_code == 200
        body = r.json()
        assert body["caso"]["estado"] == "CERRADO"
        assert body["aviso"] is None
        assert any("fue cerrado" in texto for _chat, texto in telegram.sent)

        db.refresh(caso)
        assert caso.estado == EstadoCaso.CERRADO
        assert caso.fecha_cierre is not None
        assert caso.responsable_id is not None

        # Un caso ya cerrado no se puede volver a cerrar.
        r = client.post(
            f"/api/v1/casos/{caso.id}/cerrar", headers=auth["operador"]
        )
        assert r.status_code == 409
        assert "cerrado" in r.json()["detail"]
    finally:
        _cleanup(db, ped.id)


def test_cerrar_caso_de_otro_operador_devuelve_409(client, auth, db):
    ped = _mk_pedido(db, suffix="caso7")
    caso = _mk_caso(db, ped)
    # Otro operador ya lo tomó.
    otro = db.scalar(select(Usuario).where(Usuario.email == "t.admin@example.com"))
    caso.responsable_id = otro.id
    db.commit()
    try:
        r = client.post(
            f"/api/v1/casos/{caso.id}/cerrar", headers=auth["operador"]
        )
        assert r.status_code == 409
        assert "siendo atendido" in r.json()["detail"]
    finally:
        _cleanup(db, ped.id)


def test_thread_y_chats_ignoran_mensajes_operativos(client, auth, db):
    ped = _mk_pedido(db, suffix="caso5")
    base = datetime.utcnow() - timedelta(minutes=2)
    db.add(Comunicacion(
        pedido_id=ped.id,
        direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.TELEGRAM,
        contenido="Hola, ¿cómo va mi pedido?",
        autor=AutorComunicacion.CLIENTE,
        clase=ClaseComunicacion.CLIENTE,
        escalado=False,
        fecha=base,
    ))
    db.add(Comunicacion(
        pedido_id=ped.id,
        direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.TELEGRAM,
        contenido="✅ Vinculado al pedido de prueba",
        autor=AutorComunicacion.AGENTE,
        clase=ClaseComunicacion.OPERATIVO,
        escalado=False,
        fecha=base + timedelta(seconds=30),
    ))
    db.commit()
    try:
        # Por defecto solo se ve la conversación con el cliente. El admin
        # puede auditar cualquier pedido aunque no tenga caso asignado.
        hilo = client.get(
            f"/api/v1/agent/thread?pedido_id={ped.id}", headers=auth["admin"]
        ).json()
        assert len(hilo) == 1
        assert hilo[0]["contenido"] == "Hola, ¿cómo va mi pedido?"
        assert hilo[0]["clase"] == "CLIENTE"

        # Con la bandera de auditoría aparecen ambos y se distinguen.
        hilo = client.get(
            f"/api/v1/agent/thread?pedido_id={ped.id}&incluir_operativos=true",
            headers=auth["admin"],
        ).json()
        assert [m["clase"] for m in hilo] == ["CLIENTE", "OPERATIVO"]
        assert hilo[1]["contenido"].startswith("✅")

        # La bandeja cuenta y previsualiza solo la conversación.
        chat = next(
            c for c in client.get(
                "/api/v1/agent/chats", headers=auth["admin"]
            ).json()
            if c["pedido_id"] == ped.id
        )
        assert chat["total_mensajes"] == 1
        assert chat["ultima_preview"] == "Hola, ¿cómo va mi pedido?"
    finally:
        _cleanup(db, ped.id)


# --------- Visibilidad y asignación por rol ---------
def test_operador_solo_ve_sus_chats_y_casos_mas_los_libres(client, auth, db):
    operador_id = _user_id(db, "t.oper@example.com")
    admin_id = _user_id(db, "t.admin@example.com")
    suf = uuid.uuid4().hex[:5]
    ped_propio = _mk_pedido(db, suffix=f"vis1-{suf}")
    ped_libre = _mk_pedido(db, suffix=f"vis2-{suf}")
    ped_ajeno = _mk_pedido(db, suffix=f"vis3-{suf}")
    caso_propio = _mk_caso(db, ped_propio)
    caso_propio.responsable_id = operador_id
    caso_libre = _mk_caso(db, ped_libre)
    caso_ajeno = _mk_caso(db, ped_ajeno)
    caso_ajeno.responsable_id = admin_id
    db.commit()
    try:
        chats = client.get("/api/v1/agent/chats", headers=auth["operador"])
        assert chats.status_code == 200
        ids_chats = {c["pedido_id"] for c in chats.json()}
        assert ped_propio.id in ids_chats
        assert ped_libre.id not in ids_chats
        assert ped_ajeno.id not in ids_chats

        casos = client.get("/api/v1/casos", headers=auth["operador"]).json()
        ids_casos = {c["id"] for c in casos}
        assert caso_propio.id in ids_casos
        assert caso_libre.id in ids_casos
        assert caso_ajeno.id not in ids_casos

        # El admin ve todo.
        chats_admin = client.get("/api/v1/agent/chats", headers=auth["admin"]).json()
        ids_chats_admin = {c["pedido_id"] for c in chats_admin}
        assert {ped_propio.id, ped_libre.id, ped_ajeno.id} <= ids_chats_admin
        casos_admin = client.get("/api/v1/casos", headers=auth["admin"]).json()
        ids_casos_admin = {c["id"] for c in casos_admin}
        assert {caso_propio.id, caso_libre.id, caso_ajeno.id} <= ids_casos_admin
    finally:
        for ped in (ped_propio, ped_libre, ped_ajeno):
            _cleanup(db, ped.id)


def test_thread_bloquea_caso_ajeno_pero_permite_libre(client, auth, db):
    admin_id = _user_id(db, "t.admin@example.com")
    suf = uuid.uuid4().hex[:5]
    ped_ajeno = _mk_pedido(db, suffix=f"thr1-{suf}")
    ped_libre = _mk_pedido(db, suffix=f"thr2-{suf}")
    caso_ajeno = _mk_caso(db, ped_ajeno)
    caso_ajeno.responsable_id = admin_id
    _mk_caso(db, ped_libre)
    db.commit()
    try:
        r = client.get(
            f"/api/v1/agent/thread?pedido_id={ped_ajeno.id}",
            headers=auth["operador"],
        )
        assert r.status_code == 403
        assert "otro operador" in r.json()["detail"]

        # Un caso libre se puede abrir para decidir si reclamarlo.
        r = client.get(
            f"/api/v1/agent/thread?pedido_id={ped_libre.id}",
            headers=auth["operador"],
        )
        assert r.status_code == 200

        # El admin puede auditar cualquier conversación.
        r = client.get(
            f"/api/v1/agent/thread?pedido_id={ped_ajeno.id}",
            headers=auth["admin"],
        )
        assert r.status_code == 200
    finally:
        for ped in (ped_ajeno, ped_libre):
            _cleanup(db, ped.id)


def test_admin_reasigna_y_operador_libera_caso(client, auth, db):
    operador_id = _user_id(db, "t.oper@example.com")
    admin_id = _user_id(db, "t.admin@example.com")
    ped = _mk_pedido(db, suffix=f"asig1-{uuid.uuid4().hex[:5]}")
    caso = _mk_caso(db, ped)
    try:
        # El admin asigna el caso libre al operador.
        r = client.post(
            f"/api/v1/casos/{caso.id}/reasignar",
            headers=auth["admin"],
            json={"responsable_id": operador_id},
        )
        assert r.status_code == 200
        assert r.json()["caso"]["responsable_id"] == operador_id
        db.refresh(caso)
        assert caso.responsable_id == operador_id

        audit = db.scalar(
            select(Comunicacion).where(
                Comunicacion.caso_id == caso.id,
                Comunicacion.clase == ClaseComunicacion.OPERATIVO,
            )
        )
        assert audit is not None
        assert "reasignado" in audit.contenido.lower()

        # La asignación no se puede saltar el flujo auditado por PATCH.
        r = client.patch(
            f"/api/v1/casos/{caso.id}",
            headers=auth["admin"],
            json={"responsable_id": admin_id},
        )
        assert r.status_code == 400
        assert "reasignar" in r.json()["detail"].lower()

        # El operador no puede reasignar a otro: solo liberar.
        r = client.post(
            f"/api/v1/casos/{caso.id}/reasignar",
            headers=auth["operador"],
            json={"responsable_id": admin_id},
        )
        assert r.status_code == 403

        # El operador responsable libera el caso.
        r = client.post(
            f"/api/v1/casos/{caso.id}/reasignar",
            headers=auth["operador"],
            json={"responsable_id": None},
        )
        assert r.status_code == 200
        assert r.json()["caso"]["responsable_id"] is None
        db.refresh(caso)
        assert caso.responsable_id is None

        # Un operador no puede liberar un caso libre que no es suyo.
        r = client.post(
            f"/api/v1/casos/{caso.id}/reasignar",
            headers=auth["operador"],
            json={"responsable_id": None},
        )
        assert r.status_code == 403

        # GERENTE no tiene acceso a la operación.
        r = client.post(
            f"/api/v1/casos/{caso.id}/reasignar",
            headers=auth["gerente"],
            json={"responsable_id": None},
        )
        assert r.status_code == 403
    finally:
        _cleanup(db, ped.id)


def test_human_reply_operador_sin_caso_denegado_admin_ok(client, auth, db, monkeypatch):
    ped = _mk_pedido(db, suffix=f"hrep1-{uuid.uuid4().hex[:5]}")
    ped.cliente.telegram_chat_id = "9900201"
    db.commit()
    telegram = _FakeTelegram()
    monkeypatch.setattr(
        "app.services.caso_service.TelegramService", lambda: telegram
    )
    try:
        r = client.post(
            "/api/v1/agent/human-reply",
            headers=auth["operador"],
            json={"pedido_id": ped.id, "contenido": "Hola"},
        )
        assert r.status_code == 403

        r = client.post(
            "/api/v1/agent/human-reply",
            headers=auth["admin"],
            json={"pedido_id": ped.id, "contenido": "Hola desde admin"},
        )
        assert r.status_code == 200
        assert ("9900201", "Hola desde admin") in telegram.sent
    finally:
        _cleanup(db, ped.id)


def test_cerrar_caso_ajeno_admin_si_operador_no(client, auth, db):
    admin_id = _user_id(db, "t.admin@example.com")
    ped = _mk_pedido(db, suffix=f"cerr1-{uuid.uuid4().hex[:5]}")
    caso = _mk_caso(db, ped)
    caso.responsable_id = admin_id
    db.commit()
    try:
        r = client.post(
            f"/api/v1/casos/{caso.id}/cerrar", headers=auth["operador"]
        )
        assert r.status_code == 409

        r = client.patch(
            f"/api/v1/casos/{caso.id}",
            headers=auth["operador"],
            json={"estado": "CERRADO"},
        )
        assert r.status_code == 403

        r = client.post(
            f"/api/v1/casos/{caso.id}/cerrar", headers=auth["admin"]
        )
        assert r.status_code == 200
        assert r.json()["caso"]["estado"] == "CERRADO"
        db.refresh(caso)
        assert caso.responsable_id == admin_id
    finally:
        _cleanup(db, ped.id)
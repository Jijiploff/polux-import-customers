from datetime import datetime
from types import SimpleNamespace

from app.services import hito_service


def test_completed_hito_is_dispatched_immediately_to_linked_telegram(monkeypatch):
    sent = []

    class FakeNotifier:
        def __init__(self, _db):
            pass

        def send_from_template(self, **kwargs):
            sent.append(kwargs)
            return SimpleNamespace(id=41)

    class FakeWorker:
        def __init__(self, _db):
            pass

        def process_communication(self, communication_id):
            sent.append({"communication_id": communication_id})
            return "sent"

    monkeypatch.setattr(hito_service, "NotificationService", FakeNotifier)
    monkeypatch.setattr(hito_service, "OutboxWorker", FakeWorker)

    cliente = SimpleNamespace(
        telegram_chat_id="12345",
        nombre="María",
        consentimiento_datos=True,
    )
    pedido = SimpleNamespace(
        cliente=cliente,
        codigo="PD-TEST-1",
        fecha_prometida=datetime(2026, 11, 20),
    )
    hito = SimpleNamespace(
        hito=SimpleNamespace(nombre="Preparación"),
        item=SimpleNamespace(descripcion_producto="iPhone 15"),
        notificado_cliente=False,
        fecha_notificacion=None,
    )

    hito_service._notificar_hito_completado(None, hito, pedido, 7)

    assert sent[0]["codigo_plantilla"] == "AVISO_HITO"
    assert sent[0]["pedido"] is pedido
    assert sent[1] == {"communication_id": 41}
    assert hito.notificado_cliente is True
    assert hito.fecha_notificacion is not None

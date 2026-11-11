"""Pruebas de vinculación de Telegram con código de pedido + DNI."""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.models import (
    Canal,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    EstadoIngreso,
    EstadoItem,
    EstadoPedido,
    ModalidadEntrega,
    OrigenItem,
    Pedido,
    PedidoItem,
)
from app.services.telegram_handler import _parse_pedido_link, handle_telegram_update


class FakeTelegram:
    """Doble de TelegramService que sólo registra los envíos."""

    enabled = True
    operator_chat_id = ""

    def __init__(self):
        self.sent: list[tuple[int, str]] = []

    def send_message(self, chat_id, text, **_kwargs):
        self.sent.append((int(chat_id), text))
        return SimpleNamespace(ok=True, message_id=1, error=None, retriable=False)

    def redact(self, text: str) -> str:
        return text


def _update(chat_id: int, text: str) -> dict:
    return {
        "update_id": uuid.uuid4().int % 2_000_000_000,
        "message": {"message_id": 1, "chat": {"id": chat_id}, "text": text},
    }


@pytest.fixture
def escenario():
    db = SessionLocal()
    max_com_id = db.scalar(select(func.max(Comunicacion.id))) or 0
    suf = uuid.uuid4().hex[:6]

    cliente = Cliente(
        nombre=f"TG {suf}",
        documento="70000001",
        consentimiento_datos=True,
        consentimiento_fecha=datetime.utcnow(),
    )
    db.add(cliente)
    db.flush()

    pedido = Pedido(
        codigo=f"PD-TG-{suf}",
        cliente_id=cliente.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow(),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(pedido)
    db.flush()
    db.add(PedidoItem(
        pedido_id=pedido.id,
        descripcion_producto="Producto de prueba",
        cantidad=1,
        origen=OrigenItem.STOCK_TRUJILLO,
        estado=EstadoItem.EN_PROCESO,
    ))
    db.commit()
    db.refresh(pedido)
    db.refresh(cliente)

    yield db, pedido, cliente

    db.execute(delete(Comunicacion).where(
        Comunicacion.id > max_com_id,
        Comunicacion.canal == Canal.TELEGRAM,
    ))
    db.commit()
    from tests.db_utils import cleanup_pedido
    cleanup_pedido(db, pedido.id)
    db.close()


# ---------- Parser ----------
def test_parser_codigo_solo():
    codigo, documento = _parse_pedido_link("PD-2025-0001")
    assert codigo == "PD-2025-0001"
    assert documento is None


def test_parser_codigo_y_dni():
    assert _parse_pedido_link("PD-2025-0001 70000001") == ("PD-2025-0001", "70000001")
    assert _parse_pedido_link("pd-2025-0001 DNI 70000001") == (
        "PD-2025-0001", "70000001",
    )
    assert _parse_pedido_link("PD-2025-0001, 70000001") == (
        "PD-2025-0001", "70000001",
    )


# ---------- Flujo de vinculación ----------
def test_sin_dni_pide_dni_y_no_vincula(escenario):
    db, pedido, cliente = escenario
    tg = FakeTelegram()

    result = handle_telegram_update(db, _update(1001, pedido.codigo), telegram=tg)

    assert result["handled"] == "dni_required"
    db.refresh(cliente)
    assert cliente.telegram_chat_id is None
    assert "DNI" in tg.sent[-1][1]


def test_dni_incorrecto_rechaza_sin_revelar(escenario):
    db, pedido, cliente = escenario
    tg = FakeTelegram()

    result = handle_telegram_update(
        db, _update(1002, f"{pedido.codigo} 99999999"), telegram=tg,
    )

    assert result["handled"] == "link_rejected"
    db.refresh(cliente)
    assert cliente.telegram_chat_id is None
    assert "No pudimos validar" in tg.sent[-1][1]


def test_codigo_inexistente_mensaje_generico(escenario):
    db, _pedido, _cliente = escenario
    tg = FakeTelegram()

    result = handle_telegram_update(
        db, _update(1003, "PD-9999-9999 70000001"), telegram=tg,
    )

    assert result["handled"] == "link_rejected"
    assert "No pudimos validar" in tg.sent[-1][1]


def test_dni_correcto_vincula(escenario):
    db, pedido, cliente = escenario
    tg = FakeTelegram()
    update = _update(1004, f"{pedido.codigo} 70000001")

    result = handle_telegram_update(db, update, telegram=tg)

    assert result["handled"] == "vinculado"
    db.refresh(cliente)
    assert cliente.telegram_chat_id == "1004"
    assert "Vinculado" in tg.sent[-1][1]

    contenido = db.scalar(select(Comunicacion.contenido).where(
        Comunicacion.whatsapp_message_id == f"tg:{update['update_id']}",
        Comunicacion.direccion == DireccionComunicacion.ENTRANTE,
    ))
    assert contenido is not None
    assert "70000001" not in contenido


def test_acepta_prefijo_dni(escenario):
    db, pedido, cliente = escenario
    tg = FakeTelegram()

    result = handle_telegram_update(
        db, _update(1005, f"{pedido.codigo} DNI 70000001"), telegram=tg,
    )

    assert result["handled"] == "vinculado"
    db.refresh(cliente)
    assert cliente.telegram_chat_id == "1005"


def test_no_permite_robar_pedido_ya_vinculado(escenario):
    db, pedido, cliente = escenario
    cliente.telegram_chat_id = "999"
    db.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(
        db, _update(1006, f"{pedido.codigo} 70000001"), telegram=tg,
    )

    assert result["handled"] == "already_linked"
    db.refresh(cliente)
    assert cliente.telegram_chat_id == "999"
    assert "otra cuenta" in tg.sent[-1][1]

"""Pruebas de vinculación de Telegram con código de pedido + DNI."""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select

from app.core.security import hash_password
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
    Rol,
    RolCodigo,
    Usuario,
    UsuarioRol,
)
from app.services import telegram_handler
from app.services.telegram_handler import (
    _parse_pedido_link,
    handle_telegram_update,
    notify_operator_new_caso,
)


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


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    telegram_handler._failed_attempts.clear()
    yield
    telegram_handler._failed_attempts.clear()


def _crear_operador(
    db,
    *,
    chat_id: str | None = None,
    activo: bool = True,
    con_rol: bool = True,
) -> Usuario:
    suf = uuid.uuid4().hex[:8]
    usuario = Usuario(
        email=f"op{suf}@example.com",
        nombre_completo=f"Operador {suf}",
        password_hash=hash_password("Clave123!"),
        activo=activo,
        telegram_chat_id=chat_id,
    )
    db.add(usuario)
    db.flush()
    if con_rol:
        rol = db.scalar(select(Rol).where(Rol.codigo == RolCodigo.OPERADOR))
        if rol is None:
            rol = Rol(codigo=RolCodigo.OPERADOR, nombre="Operador")
            db.add(rol)
            db.flush()
        db.add(UsuarioRol(usuario_id=usuario.id, rol_id=rol.id))
    db.commit()
    db.refresh(usuario)
    return usuario


def _borrar_usuarios(db, ids: list[int]) -> None:
    db.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id.in_(ids)))
    db.execute(delete(Usuario).where(Usuario.id.in_(ids)))
    db.commit()


@pytest.fixture
def operador():
    db = SessionLocal()
    max_com_id = db.scalar(select(func.max(Comunicacion.id))) or 0
    usuario = _crear_operador(db)
    yield db, usuario
    db.execute(delete(Comunicacion).where(
        Comunicacion.id > max_com_id,
        Comunicacion.canal == Canal.TELEGRAM,
    ))
    db.commit()
    _borrar_usuarios(db, [usuario.id])
    db.close()


@pytest.fixture
def operadores():
    db = SessionLocal()
    usuarios = [
        _crear_operador(db, chat_id="3001"),
        _crear_operador(db, chat_id="3002"),
    ]
    yield db, usuarios
    _borrar_usuarios(db, [u.id for u in usuarios])
    db.close()


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


# ---------- Operadores (vinculación por credenciales) ----------
def test_operador_se_vincula_con_sus_credenciales(operador):
    db, usuario = operador
    tg = FakeTelegram()

    result = handle_telegram_update(
        db,
        _update(2001, f"/vincular {usuario.email} Clave123!"),
        telegram=tg,
    )

    assert result["handled"] == "operator_linked"
    db.refresh(usuario)
    assert usuario.telegram_chat_id == "2001"
    assert "Vinculado como operador" in tg.sent[-1][1]


def test_operador_password_incorrecta_no_vincula(operador):
    db, usuario = operador
    tg = FakeTelegram()

    result = handle_telegram_update(
        db,
        _update(2002, f"/vincular {usuario.email} Incorrecta!"),
        telegram=tg,
    )

    assert result["handled"] == "operator_link_rejected"
    db.refresh(usuario)
    assert usuario.telegram_chat_id is None
    assert "No pudimos validar" in tg.sent[-1][1]


def test_operador_inactivo_no_vincula(operador):
    db, usuario = operador
    usuario.activo = False
    db.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(
        db,
        _update(2003, f"/vincular {usuario.email} Clave123!"),
        telegram=tg,
    )

    assert result["handled"] == "operator_link_rejected"
    db.refresh(usuario)
    assert usuario.telegram_chat_id is None


def test_usuario_sin_rol_operador_no_vincula(operador):
    db, usuario = operador
    db.execute(delete(UsuarioRol).where(UsuarioRol.usuario_id == usuario.id))
    db.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(
        db,
        _update(2004, f"/vincular {usuario.email} Clave123!"),
        telegram=tg,
    )

    assert result["handled"] == "operator_link_rejected"
    db.refresh(usuario)
    assert usuario.telegram_chat_id is None


def test_chat_no_puede_robar_vinculacion_de_otro(operador):
    db, usuario = operador
    otro = _crear_operador(db, chat_id="2007")
    try:
        tg = FakeTelegram()
        result = handle_telegram_update(
            db,
            _update(2007, f"/vincular {usuario.email} Clave123!"),
            telegram=tg,
        )

        assert result["handled"] == "operator_chat_taken"
        db.refresh(usuario)
        assert usuario.telegram_chat_id is None
        assert "otro usuario" in tg.sent[-1][1]
    finally:
        _borrar_usuarios(db, [otro.id])


def test_password_no_se_persiste_en_comunicacion(operador):
    db, usuario = operador
    tg = FakeTelegram()
    update = _update(2005, f"/vincular {usuario.email} Clave123!")

    handle_telegram_update(db, update, telegram=tg)

    contenidos = db.scalars(select(Comunicacion.contenido).where(
        Comunicacion.whatsapp_message_id == f"tg:{update['update_id']}",
    )).all()
    assert contenidos
    assert all("Clave123!" not in c for c in contenidos)


def test_bloquea_tras_cinco_intentos_fallidos(operador):
    db, usuario = operador
    tg = FakeTelegram()

    for i in range(5):
        handle_telegram_update(
            db,
            _update(2100, f"/vincular {usuario.email} Incorrecta!"),
            telegram=tg,
        )

    result = handle_telegram_update(
        db,
        _update(2100, f"/vincular {usuario.email} Clave123!"),
        telegram=tg,
    )

    assert result["handled"] == "operator_rate_limited"
    db.refresh(usuario)
    assert usuario.telegram_chat_id is None


def test_desvincula_chat_de_operador(operador):
    db, usuario = operador
    usuario.telegram_chat_id = "2006"
    db.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(db, _update(2006, "/desvincular"), telegram=tg)

    assert result["handled"] == "operator_unlinked"
    db.refresh(usuario)
    assert usuario.telegram_chat_id is None


def test_notificacion_llega_a_todos_los_operadores(operadores):
    db, _usuarios = operadores
    caso = SimpleNamespace(
        id=99,
        motivo=SimpleNamespace(value="RECLAMO"),
        prioridad=SimpleNamespace(value="ALTA"),
        descripcion="Caso de prueba",
    )
    pedido = SimpleNamespace(
        codigo="PD-TEST-0001",
        cliente=SimpleNamespace(nombre="Cliente"),
    )
    tg = FakeTelegram()

    notify_operator_new_caso(caso, pedido, telegram=tg, db=db)

    assert {chat for chat, _texto in tg.sent} == {3001, 3002}


def test_notificacion_incluye_fallback_de_env(operadores):
    db, _usuarios = operadores
    caso = SimpleNamespace(
        id=100,
        motivo=SimpleNamespace(value="RETRASO"),
        prioridad=SimpleNamespace(value="MEDIA"),
        descripcion="Caso de prueba",
    )
    pedido = SimpleNamespace(
        codigo="PD-TEST-0002",
        cliente=SimpleNamespace(nombre="Cliente"),
    )
    tg = FakeTelegram()
    tg.operator_chat_id = "9999"

    notify_operator_new_caso(caso, pedido, telegram=tg, db=db)

    assert {chat for chat, _texto in tg.sent} == {3001, 3002, 9999}

"""Pruebas de vinculación de Telegram con código de pedido + DNI."""
import uuid
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, func, select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import (
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    CasoTelegramNotificacion,
    Cliente,
    Comunicacion,
    DireccionComunicacion,
    EstadoCaso,
    EstadoIngreso,
    EstadoItem,
    EstadoPedido,
    ModalidadEntrega,
    MotivoEscalamiento,
    OrigenItem,
    Pedido,
    PedidoItem,
    PrioridadCaso,
    Rol,
    RolCodigo,
    Usuario,
    UsuarioCasoActivo,
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
        self.calls: list[dict] = []
        self.answered: list[tuple[str, str | None]] = []
        self._message_id = 100

    def send_message(self, chat_id, text, **kwargs):
        self._message_id += 1
        self.sent.append((int(chat_id), text))
        self.calls.append({
            "chat_id": int(chat_id),
            "text": text,
            "message_id": self._message_id,
            **kwargs,
        })
        return SimpleNamespace(
            ok=True, message_id=self._message_id, error=None, retriable=False,
        )

    def answer_callback_query(self, callback_query_id, text=None, **_kwargs):
        self.answered.append((str(callback_query_id), text))
        return {"ok": True}

    def redact(self, text: str) -> str:
        return text


def _update(
    chat_id: int,
    text: str,
    *,
    message_id: int = 1,
    reply_to: int | None = None,
) -> dict:
    message = {
        "message_id": message_id,
        "chat": {"id": chat_id},
        "text": text,
    }
    if reply_to is not None:
        message["reply_to_message"] = {"message_id": reply_to}
    return {
        "update_id": uuid.uuid4().int % 2_000_000_000,
        "message": message,
    }


def _callback_update(chat_id: int, data: str, *, message_id: int = 10) -> dict:
    return {
        "update_id": uuid.uuid4().int % 2_000_000_000,
        "callback_query": {
            "id": f"cb-{uuid.uuid4().hex[:8]}",
            "data": data,
            "message": {
                "message_id": message_id,
                "chat": {"id": chat_id},
            },
        },
    }


def _crear_caso(
    db,
    pedido: Pedido,
    *,
    prioridad: PrioridadCaso = PrioridadCaso.ALTA,
) -> CasoEscalamiento:
    caso = CasoEscalamiento(
        pedido_id=pedido.id,
        motivo=MotivoEscalamiento.RECLAMO,
        prioridad=prioridad,
        descripcion="Caso de prueba del bot",
        fecha_apertura=datetime.utcnow(),
        estado=EstadoCaso.ABIERTO,
    )
    db.add(caso)
    db.commit()
    db.refresh(caso)
    return caso


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

    assert {3001, 3002} <= {chat for chat, _texto in tg.sent}


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

    assert {3001, 3002, 9999} <= {chat for chat, _texto in tg.sent}


# ---------- Respuesta de operadores a casos ----------
def test_notificacion_guarda_botones_y_mapeo(operadores, escenario):
    _db_ops, _usuarios = operadores
    db, pedido, _cliente = escenario
    caso = _crear_caso(db, pedido)
    tg = FakeTelegram()

    notify_operator_new_caso(caso, pedido, telegram=tg, db=db)

    llamada = next(c for c in tg.calls if c["chat_id"] == 3001)
    assert "inline_keyboard" in llamada["reply_markup"]
    botones = llamada["reply_markup"]["inline_keyboard"]
    assert any("Ver caso" in b["text"] for fila in botones for b in fila)
    assert any("Responder" in b["text"] for fila in botones for b in fila)

    fila = db.scalar(
        select(CasoTelegramNotificacion).where(
            CasoTelegramNotificacion.chat_id == "3001",
            CasoTelegramNotificacion.message_id == llamada["message_id"],
        )
    )
    assert fila is not None
    assert fila.caso_id == caso.id


def test_callback_ver_muestra_datos_y_timeline(operador, escenario):
    db, usuario = operador
    db2, pedido, _cliente = escenario
    usuario.telegram_chat_id = "4001"
    db.commit()
    caso = _crear_caso(db2, pedido)
    tg = FakeTelegram()

    result = handle_telegram_update(
        db2, _callback_update(4001, f"caso:{caso.id}:ver"), telegram=tg,
    )

    assert result["handled"] == "callback_case_view"
    texto = tg.sent[-1][1]
    assert f"Caso #{caso.id}" in texto
    assert pedido.codigo in texto
    assert "Últimos eventos" in texto
    assert tg.answered


def test_callback_responder_y_mensaje_llega_al_cliente(operador, escenario):
    db, usuario = operador
    db2, pedido, cliente = escenario
    usuario.telegram_chat_id = "4002"
    cliente.telegram_chat_id = "5000"
    db.commit()
    db2.commit()
    caso = _crear_caso(db2, pedido)
    tg = FakeTelegram()

    handle_telegram_update(
        db2, _callback_update(4002, f"caso:{caso.id}:responder"), telegram=tg,
    )

    activo = db2.get(UsuarioCasoActivo, usuario.id)
    assert activo is not None
    assert activo.caso_id == caso.id

    result = handle_telegram_update(
        db2, _update(4002, "Hola, ya estamos revisando tu caso."), telegram=tg,
    )

    assert result["handled"] == "operator_replied"
    assert (5000, "Hola, ya estamos revisando tu caso.") in tg.sent

    db2.refresh(caso)
    assert caso.responsable_id == usuario.id
    assert caso.estado == EstadoCaso.EN_PROCESO
    assert caso.fecha_primera_accion is not None

    com = db2.scalar(
        select(Comunicacion).where(
            Comunicacion.pedido_id == pedido.id,
            Comunicacion.direccion == DireccionComunicacion.SALIENTE,
            Comunicacion.autor == AutorComunicacion.HUMANO,
        )
    )
    assert com is not None
    assert com.canal == Canal.TELEGRAM
    assert com.estado_entrega == "SENT"
    assert com.caso_id == caso.id


def test_respuesta_citando_el_aviso_del_caso(operador, escenario):
    db, usuario = operador
    db2, pedido, cliente = escenario
    usuario.telegram_chat_id = "4003"
    cliente.telegram_chat_id = "5001"
    db.commit()
    db2.commit()
    caso = _crear_caso(db2, pedido)
    db2.add(CasoTelegramNotificacion(
        caso_id=caso.id,
        usuario_id=usuario.id,
        chat_id="4003",
        message_id=77,
    ))
    db2.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(
        db2,
        _update(4003, "Respuesta citando el aviso", reply_to=77),
        telegram=tg,
    )

    assert result["handled"] == "operator_replied"
    assert (5001, "Respuesta citando el aviso") in tg.sent


def test_segundo_operador_no_puede_responder_caso_asignado(operadores, escenario):
    _db_ops, usuarios = operadores
    db, pedido, cliente = escenario
    usuario1, usuario2 = usuarios
    usuario1.telegram_chat_id = "3001"
    usuario2.telegram_chat_id = "3002"
    _db_ops.commit()
    cliente.telegram_chat_id = "5002"
    db.commit()
    caso = _crear_caso(db, pedido)
    caso.responsable_id = usuario1.id
    db.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(
        db, _update(3002, f"/responder {caso.id} Intento duplicado"), telegram=tg,
    )

    assert result["handled"] == "operator_reply_rejected"
    assert result["code"] == "asignado"
    assert "siendo atendido" in tg.sent[-1][1]
    assert (5002, "Intento duplicado") not in tg.sent


def test_responder_sin_telegram_del_cliente_avisa(operador, escenario):
    db, usuario = operador
    db2, pedido, cliente = escenario
    usuario.telegram_chat_id = "4004"
    cliente.telegram_chat_id = None
    db.commit()
    db2.commit()
    caso = _crear_caso(db2, pedido)
    tg = FakeTelegram()

    result = handle_telegram_update(
        db2, _update(4004, f"/responder {caso.id} Hola"), telegram=tg,
    )

    assert result["handled"] == "operator_reply_rejected"
    assert result["code"] == "sin_telegram"
    assert "Telegram" in tg.sent[-1][1]


def test_cerrar_caso_desde_boton(operador, escenario):
    db, usuario = operador
    db2, pedido, cliente = escenario
    usuario.telegram_chat_id = "4005"
    cliente.telegram_chat_id = "5003"
    db.commit()
    db2.commit()
    caso = _crear_caso(db2, pedido)
    db2.add(UsuarioCasoActivo(usuario_id=usuario.id, caso_id=caso.id))
    db2.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(
        db2, _callback_update(4005, f"caso:{caso.id}:cerrar"), telegram=tg,
    )

    assert result["handled"] == "operator_closed"
    db2.refresh(caso)
    assert caso.estado == EstadoCaso.CERRADO
    assert caso.fecha_cierre is not None
    assert db2.get(UsuarioCasoActivo, usuario.id) is None
    assert any("fue cerrado" in texto for chat, texto in tg.sent if chat == 5003)


def test_comandos_casos_y_detalle(operador, escenario):
    db, usuario = operador
    db2, pedido, _cliente = escenario
    usuario.telegram_chat_id = "4006"
    db.commit()
    caso = _crear_caso(db2, pedido)
    tg = FakeTelegram()

    r1 = handle_telegram_update(db2, _update(4006, "/casos"), telegram=tg)
    assert r1["handled"] == "operator_cases"
    assert f"#{caso.id}" in tg.sent[-1][1]

    r2 = handle_telegram_update(
        db2, _update(4006, f"/caso {caso.id}"), telegram=tg,
    )
    assert r2["handled"] == "operator_case"
    assert "Caso de prueba del bot" in tg.sent[-1][1]


def test_salir_limpia_el_caso_activo(operador, escenario):
    db, usuario = operador
    db2, pedido, _cliente = escenario
    usuario.telegram_chat_id = "4007"
    db.commit()
    caso = _crear_caso(db2, pedido)
    db2.add(UsuarioCasoActivo(usuario_id=usuario.id, caso_id=caso.id))
    db2.commit()
    tg = FakeTelegram()

    result = handle_telegram_update(db2, _update(4007, "/salir"), telegram=tg)

    assert result["handled"] == "operator_exit"
    assert db2.get(UsuarioCasoActivo, usuario.id) is None


def test_mensaje_del_cliente_se_reenvia_y_operador_responde(operador, escenario):
    """Chat bidireccional: cliente → operador (aviso) → cliente (respuesta)."""
    db, usuario = operador
    db2, pedido, cliente = escenario
    usuario.telegram_chat_id = "4100"
    cliente.telegram_chat_id = "5100"
    db.commit()
    db2.commit()
    caso = _crear_caso(db2, pedido)
    caso.responsable_id = usuario.id
    db2.commit()
    tg = FakeTelegram()

    update = _update(5100, "Ya pagué, ¿qué sigue?")
    result = handle_telegram_update(db2, update, telegram=tg)

    assert result["handled"] == "case_message_forwarded"
    assert result["caso_id"] == caso.id
    aviso = next(c for c in tg.calls if c["chat_id"] == 4100)
    assert "Ya pagué" in aviso["text"]
    assert "inline_keyboard" in aviso["reply_markup"]
    # El agente no responde: el mensaje queda en manos del operador.
    assert all(chat != 5100 for chat, _texto in tg.sent)

    entrada = db2.scalar(
        select(Comunicacion).where(
            Comunicacion.pedido_id == pedido.id,
            Comunicacion.direccion == DireccionComunicacion.ENTRANTE,
            Comunicacion.whatsapp_message_id == f"tg:{update['update_id']}",
        )
    )
    assert entrada is not None
    assert entrada.caso_id == caso.id
    assert entrada.autor == AutorComunicacion.CLIENTE

    # El operador responde citando el aviso y el cliente lo recibe.
    result2 = handle_telegram_update(
        db2,
        _update(4100, "Tu pedido sigue en proceso.", reply_to=aviso["message_id"]),
        telegram=tg,
    )
    assert result2["handled"] == "operator_replied"
    assert (5100, "Tu pedido sigue en proceso.") in tg.sent


def test_mensaje_de_caso_sin_asignar_se_reenvia_a_todos(operadores, escenario):
    _db_ops, _usuarios = operadores
    db, pedido, cliente = escenario
    cliente.telegram_chat_id = "5101"
    db.commit()
    _crear_caso(db, pedido)
    tg = FakeTelegram()

    result = handle_telegram_update(
        db, _update(5101, "¿Alguien me puede ayudar?"), telegram=tg,
    )

    assert result["handled"] == "case_message_forwarded"
    chats = {chat for chat, _texto in tg.sent}
    assert {3001, 3002} <= chats

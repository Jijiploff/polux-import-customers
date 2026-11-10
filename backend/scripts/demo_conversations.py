"""10 conversaciones de prueba para el simulador de WhatsApp (Fase G3).

Combina los tres tipos de hilo que describe la manual de usuario:

- **Quejas (4)** — PD-2025-0002 (demo, ya resuelto), PD-2025-0004 (daño de
  producto), PD-2025-0007 (demora, se resuelve) y PD-2025-0010 (cobro
  incorrecto, recién abierto). En todos, el agente clasifica con
  sentimiento NEGATIVO / intención RECLAMO, **escala a caso** y responde con
  el mensaje de holding; los casos reciben respuesta humana según corresponde.
- **Seguimientos normales (4)** — PD-2025-0001, PD-2025-0003, PD-2025-0005 y
  PD-2025-0008: consultas de estado/retraso con sentimiento NEUTRO que el
  agente responde con datos reales (estado, fecha prometida, ítems) **sin
  escalar**.
- **Conversaciones positivas (2)** — PD-2025-0006 y PD-2025-0009:
  agradecimientos y felicitaciones con respuesta cordial, sin escalamiento.

Reglas de negocio respetadas (el motor de reglas corre cada 5 min localmente
y debe encontrar el dato "limpio"):

1. Toda entrante con `sentimiento=NEGATIVO` o `intencion=RECLAMO` lleva
   `caso_id` (si no, `_rule_reclamo_tono_negativo` abriría otro caso).
2. Cada pedido activo recibe su saliente con plantilla BIENVENIDA
   (`_rule_bienvenida` no debe volver a enviarla).
3. Los hitos nuevos quedan PENDIENTE con `fecha_prevista` en el futuro
   (`registrar_atrasos` marcaría ATRASADO y saltarían alertas de retraso).
4. Ningún pedido nuevo tiene todos los ítems LISTO_PARA_ENTREGA
   (`_rule_entrega_lista` mandaría ENTREGA_LISTA); todos quedan EN_PROCESO
   (la regla de silencio sólo aplica a EN_COORDINACION).
5. El último mensaje de cada hilo es reciente (< 3 días) para que no se
   dispare `ACTUALIZACION_PERIODICA`.
6. Las respuestas salientes quedan `estado_entrega=SENT` con `enviado_en`
   (el outbox worker no las vuelve a tomar) y los casos respetan
   apertura ≤ primera acción ≤ cierre.

Ejecutar: `python -m scripts.demo_conversations` (idempotente, no corre en
producción). Al final sincroniza los hechos (`fact_*`) para los KPIs.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import (
    AutorComunicacion,
    Canal,
    CasoEscalamiento,
    Cliente,
    Comunicacion,
    Contrato,
    DireccionComunicacion,
    EstadoCaso,
    EstadoHito,
    EstadoIngreso,
    EstadoItem,
    EstadoPedido,
    HitoCatalogo,
    ItemHito,
    ModalidadEntrega,
    MotivoEscalamiento,
    OrigenItem,
    Pedido,
    PedidoItem,
    PlantillaMensaje,
    PrioridadCaso,
    Producto,
    Sentimiento,
    SlaHito,
    Usuario,
)
from app.services.fact_sync_service import FactSyncService

# Detalle de los 4 productos del catálogo (crea `scripts.test_data` si faltan).
_SKU_DETALLE = {
    "AIRPODSPRO2": dict(modelo="AirPods Pro 2", color="Blanco", capacidad=None,
                        accesorios="Cable USB-C, estuche MagSafe"),
    "IPHONE15-128-BLU": dict(modelo="iPhone 15", color="Azul", capacidad="128GB",
                             accesorios="Cable USB-C"),
    "IPHONE15PM-256-BLK": dict(modelo="iPhone 15 Pro Max", color="Negro Titanio",
                               capacidad="256GB", accesorios="Cable USB-C"),
    "MACBOOKAIR-M3": dict(modelo="MacBook Air M3 13\"", color="Medianoche",
                          capacidad="512GB",
                          accesorios="Cargador 35W, cable USB-C"),
}

# (codigo, documento, nombre, tel, email, contrato, monto, sku, origen,
#  días_ingreso, días_promesa, modalidad, dirección, estado_ingreso)
_NUEVOS = [
    ("PD-2025-0004", "70000003", "Lucía Fernández", "+51987000003",
     "lucia@example.com", "CT-2025-003", "189.00", "AIRPODSPRO2",
     OrigenItem.STOCK_TRUJILLO, 3, 10, ModalidadEntrega.DOMICILIO,
     "Av. Washington 455, Trujillo", EstadoIngreso.PAGO_COMPLETO_VERIFICADO),
    ("PD-2025-0005", "70000004", "Jorge Quispe", "+51987000004",
     "jorge@example.com", "CT-2025-004", "799.00", "IPHONE15-128-BLU",
     OrigenItem.IMPORTACION, 2, 18, ModalidadEntrega.RECOJO,
     "Jr. Bolognesi 210, Trujillo", EstadoIngreso.PRIMER_PAGO_VERIFICADO),
    ("PD-2025-0006", "70000005", "Andrea Salazar", "+51987000005",
     "andrea@example.com", "CT-2025-005", "1199.00", "IPHONE15PM-256-BLK",
     OrigenItem.IMPORTACION, 4, 21, ModalidadEntrega.DOMICILIO,
     "Av. España 1220, Trujillo", EstadoIngreso.PAGO_COMPLETO_VERIFICADO),
    ("PD-2025-0007", "70000006", "Camila Rojas", "+51987000006",
     "camila@example.com", "CT-2025-006", "1099.00", "MACBOOKAIR-M3",
     OrigenItem.IMPORTACION, 10, 12, ModalidadEntrega.DOMICILIO,
     "Urb. Villa Serena Mz. B, Trujillo", EstadoIngreso.PAGO_COMPLETO_VERIFICADO),
    ("PD-2025-0008", "70000007", "Renzo Torres", "+51987000007",
     "renzo@example.com", "CT-2025-007", "1199.00", "IPHONE15PM-256-BLK",
     OrigenItem.IMPORTACION, 6, 9, ModalidadEntrega.RECOJO,
     "Av. Mansiche 778, Trujillo", EstadoIngreso.PRIMER_PAGO_VERIFICADO),
    ("PD-2025-0009", "70000008", "Valeria Cruz", "+51987000008",
     "valeria@example.com", "CT-2025-008", "249.00", "AIRPODSPRO2",
     OrigenItem.STOCK_TRUJILLO, 2, 6, ModalidadEntrega.DOMICILIO,
     "Jr. San Martín 340, Trujillo", EstadoIngreso.PAGO_COMPLETO_VERIFICADO),
    ("PD-2025-0010", "70000009", "Marco Espinoza", "+51987000009",
     "marco@example.com", "CT-2025-009", "799.00", "IPHONE15-128-BLU",
     OrigenItem.IMPORTACION, 5, 15, ModalidadEntrega.RECOJO,
     "Av. Principal s/n, Huanchaco", EstadoIngreso.PRIMER_PAGO_VERIFICADO),
]


def _now() -> datetime:
    return datetime.utcnow()


def _antes(dt: datetime, corte: datetime) -> datetime:
    """Nunca produce fechas futuras (importa si el script corre temprano)."""
    return min(dt, corte - timedelta(minutes=5))


# ---------------------------------------------------------------- helpers
def _cliente(db, documento: str, nombre: str, tel: str, email: str) -> Cliente:
    c = db.scalar(select(Cliente).where(Cliente.documento == documento))
    if c is None:
        c = Cliente(
            documento=documento, nombre=nombre,
            telefono_whatsapp=tel, email=email,
            consentimiento_datos=True, consentimiento_fecha=_now(),
        )
        db.add(c)
        db.flush()
    return c


def _contrato(db, numero: str, cliente_id: int, monto: str) -> Contrato:
    c = db.scalar(select(Contrato).where(Contrato.numero == numero))
    if c is None:
        c = Contrato(
            numero=numero, cliente_id=cliente_id,
            fecha_firma=(_now() - timedelta(days=20)).date(),
            monto_total=Decimal(monto), moneda="USD",
        )
        db.add(c)
        db.flush()
    return c


def _producto(db, sku: str) -> Producto:
    p = db.scalar(select(Producto).where(Producto.sku == sku))
    if p is None:  # pragma: no cover - test_data ya los crea
        raise SystemExit(f"[g3] Falta el producto {sku} — ejecuta scripts.test_data.")
    return p


def _pedido(db, **kw) -> tuple[Pedido, bool]:
    p = db.scalar(select(Pedido).where(Pedido.codigo == kw["codigo"]))
    if p is not None:
        return p, False
    p = Pedido(**kw)
    db.add(p)
    db.flush()
    return p, True


def _item(db, pedido: Pedido, producto: Producto, origen: OrigenItem) -> PedidoItem:
    it = db.scalar(
        select(PedidoItem).where(
            PedidoItem.pedido_id == pedido.id,
            PedidoItem.descripcion_producto == producto.nombre,
        )
    )
    if it is None:
        d = _SKU_DETALLE[producto.sku]
        it = PedidoItem(
            pedido_id=pedido.id, producto_id=producto.id,
            descripcion_producto=producto.nombre, cantidad=1,
            origen=origen, estado=EstadoItem.EN_PROCESO, **d,
        )
        db.add(it)
        db.flush()
    return it


def _hitos_futuros(db, pedido: Pedido, item: PedidoItem) -> int:
    """Hitos PENDIENTE con fecha_prevista siempre en el futuro (regla 3)."""
    ahora = _now()
    prev = max(pedido.fecha_ingreso, ahora - timedelta(days=1))
    cat = db.scalars(
        select(HitoCatalogo)
        .where(HitoCatalogo.origen == item.origen, HitoCatalogo.activo == True)  # noqa: E712
        .order_by(HitoCatalogo.orden)
    ).all()
    creados = 0
    for h in cat[:4]:
        ya = db.scalar(
            select(ItemHito).where(
                ItemHito.pedido_item_id == item.id, ItemHito.hito_id == h.id
            )
        )
        if ya is not None:
            continue
        sla = db.scalar(
            select(SlaHito).where(
                SlaHito.hito_id == h.id, SlaHito.origen == item.origen
            )
        )
        prev = max(
            prev + timedelta(days=(sla.dias_maximos if sla else 1)),
            ahora + timedelta(days=1),
        )
        db.add(ItemHito(
            pedido_item_id=item.id, hito_id=h.id,
            fecha_prevista=prev, estado=EstadoHito.PENDIENTE,
        ))
        creados += 1
    return creados


def _plantilla(db, codigo: str) -> PlantillaMensaje:
    p = db.scalar(select(PlantillaMensaje).where(PlantillaMensaje.codigo == codigo))
    if p is None:  # pragma: no cover - seed_data crea las plantillas
        raise SystemExit(f"[g3] Falta la plantilla {codigo} — ejecuta scripts.seed_data.")
    return p


def _entrante(
    db, pedido: Pedido, contenido: str, *,
    intencion: str, sentimiento: Sentimiento, fecha: datetime,
    caso: CasoEscalamiento | None = None,
) -> Comunicacion:
    existe = db.scalar(
        select(Comunicacion).where(
            Comunicacion.pedido_id == pedido.id,
            Comunicacion.direccion == DireccionComunicacion.ENTRANTE,
            Comunicacion.contenido == contenido,
        )
    )
    if existe is not None:
        return existe
    com = Comunicacion(
        pedido_id=pedido.id, direccion=DireccionComunicacion.ENTRANTE,
        canal=Canal.WHATSAPP, contenido=contenido,
        intencion_detectada=intencion, sentimiento=sentimiento,
        autor=AutorComunicacion.CLIENTE, fecha=fecha,
        escalado=caso is not None, caso_id=caso.id if caso else None,
    )
    db.add(com)
    db.flush()
    return com


def _saliente(
    db, pedido: Pedido, contenido: str, *,
    fecha: datetime, autor: AutorComunicacion = AutorComunicacion.AGENTE,
    plantilla: str | None = None, intencion: str | None = None,
    sentimiento: Sentimiento | None = None,
    caso: CasoEscalamiento | None = None, escalado: bool = False,
    usuario_id: int | None = None,
) -> Comunicacion:
    existe = db.scalar(
        select(Comunicacion).where(
            Comunicacion.pedido_id == pedido.id,
            Comunicacion.direccion == DireccionComunicacion.SALIENTE,
            Comunicacion.contenido == contenido,
        )
    )
    if existe is not None:
        return existe
    com = Comunicacion(
        pedido_id=pedido.id, direccion=DireccionComunicacion.SALIENTE,
        canal=Canal.WHATSAPP, contenido=contenido,
        intencion_detectada=intencion, sentimiento=sentimiento,
        autor=autor, usuario_id=usuario_id,
        plantilla_id=_plantilla(db, plantilla).id if plantilla else None,
        estado_entrega="SENT", enviado_en=fecha,
        escalado=escalado, caso_id=caso.id if caso else None,
        fecha=fecha,
    )
    db.add(com)
    db.flush()
    return com


def _caso(
    db, *, pedido: Pedido, prioridad: PrioridadCaso, descripcion: str,
    apertura: datetime, origen: Comunicacion,
    primera: datetime | None = None, cierre: datetime | None = None,
    estado: EstadoCaso, admin_id: int | None, operador_id: int | None,
) -> CasoEscalamiento:
    existe = db.scalar(
        select(CasoEscalamiento).where(
            CasoEscalamiento.pedido_id == pedido.id,
            CasoEscalamiento.motivo == MotivoEscalamiento.RECLAMO,
            CasoEscalamiento.descripcion == descripcion,
        )
    )
    if existe is not None:
        return existe
    caso = CasoEscalamiento(
        pedido_id=pedido.id, comunicacion_origen_id=origen.id,
        motivo=MotivoEscalamiento.RECLAMO, prioridad=prioridad,
        descripcion=descripcion, fecha_apertura=apertura,
        fecha_primera_accion=primera, fecha_cierre=cierre, estado=estado,
        responsable_id=operador_id if primera else None,
        created_by_id=admin_id,
        updated_by_id=admin_id if estado == EstadoCaso.RESUELTO else None,
    )
    db.add(caso)
    db.flush()
    return caso


def _bienvenida(db, pedido: Pedido, fecha: datetime) -> None:
    """Saliente BIENVENIDA (regla 2) con el texto renderizado de la plantilla."""
    p = pedido
    resumen = ", ".join(
        f"{i.cantidad}x {i.descripcion_producto}" for i in p.items
    ) or "(sin ítems)"
    _saliente(
        db, p,
        f"Hola {p.cliente.nombre}, te damos la bienvenida a Polux Import. "
        f"Tu pedido {p.codigo} fue verificado. Ítems: {resumen}. "
        f"Fecha prometida: {p.fecha_prometida.strftime('%d/%m/%Y')}. "
        "Te mantendremos informado.",
        fecha=fecha, plantilla="BIENVENIDA",
    )


def _holding(db, pedido: Pedido, fecha: datetime, caso) -> None:
    _saliente(
        db, pedido,
        f"Hola {pedido.cliente.nombre}, hemos derivado tu caso con un asesor "
        "que te contactará en breve.",
        fecha=fecha, plantilla="AGENTE_HOLDING_ESCALAMIENTO",
        escalado=True, caso=caso,
    )


# ---------------------------------------------------------------- run
def run() -> None:
    settings = get_settings()
    if settings.APP_ENV.lower() == "production":
        raise SystemExit("demo_conversations no corre en producción.")

    db = SessionLocal()
    try:
        ahora = _now()
        admin = db.scalar(select(Usuario).where(Usuario.email == "admin@poluximport.pe"))
        oper = db.scalar(select(Usuario).where(Usuario.email == "operador@poluximport.pe"))
        admin_id = admin.id if admin else None
        oper_id = oper.id if oper else None

        def pedido(codigo: str) -> Pedido:
            p = db.scalar(select(Pedido).where(Pedido.codigo == codigo))
            if p is None:
                raise SystemExit(f"[g3] Falta el pedido {codigo} — ejecuta scripts.test_data.")
            return p

        p1, p2, p3 = pedido("PD-2025-0001"), pedido("PD-2025-0002"), pedido("PD-2025-0003")

        # ---------------------------------------------------------- 1.
        # 7 pedidos nuevos (PD-2025-0004..0010) con su cliente, contrato,
        # ítem e hitos PENDIENTE a futuro.
        nuevos: dict[str, Pedido] = {}
        for (codigo, doc, nombre, tel, email, ct, monto, sku, origen,
             dias_in, dias_pr, modalidad, direccion, estado_ing) in _NUEVOS:
            cl = _cliente(db, doc, nombre, tel, email)
            ctto = _contrato(db, ct, cl.id, monto)
            p, creado = _pedido(
                db, codigo=codigo, contrato_id=ctto.id, cliente_id=cl.id,
                estado_ingreso=estado_ing, estado_actual=EstadoPedido.EN_PROCESO,
                fecha_ingreso=ahora - timedelta(days=dias_in),
                fecha_prometida=ahora + timedelta(days=dias_pr),
                modalidad_entrega=modalidad, direccion_entrega=direccion,
                consentimiento_comunicaciones=True,
            )
            it = _item(db, p, _producto(db, sku), origen)
            if creado:
                n = _hitos_futuros(db, p, it)
                print(f"[g3] pedido {codigo} creado ({n} hitos a futuro)")
            nuevos[codigo] = p
        db.flush()

        # ---------------------------------------------------------- 2.
        # BIENVENIDA de cada pedido nuevo (regla 2 — idempotente).
        for p in nuevos.values():
            _bienvenida(db, p, _antes(p.fecha_ingreso + timedelta(minutes=5), ahora))

        # ---------------------------------------------------------- 3.
        # HILO A — PD-2025-0004 · queja DAÑO (caso CRÍTICO en proceso)
        p4 = nuevos["PD-2025-0004"]
        c1 = _entrante(
            db, p4,
            "Hola, ayer recibí mi pedido pero el estuche de los AirPods llegó "
            "abierto y con una rayada profunda. No me parece normal, ¿qué hago?",
            intencion="DAÑO", sentimiento=Sentimiento.NEGATIVO,
            fecha=ahora - timedelta(days=1, hours=2),
        )
        # Como en el flujo real: la entrante se crea primero y la escalada le
        # fija `escalado` + `caso_id` (regla 1 — si no, el motor abriría otro).
        fecha4_accion = c1.fecha + timedelta(minutes=40)
        caso4 = _caso(
            db, pedido=p4, prioridad=PrioridadCaso.CRITICA,
            descripcion="Agente detectó DAÑO. Escalar sin resolver.",
            apertura=c1.fecha, origen=c1,
            estado=EstadoCaso.EN_PROCESO, admin_id=admin_id, operador_id=oper_id,
            primera=fecha4_accion,
        )
        c1.escalado, c1.caso_id = True, caso4.id
        _holding(db, p4, c1.fecha + timedelta(seconds=20), caso4)
        _saliente(
            db, p4,
            "Hola Lucía, lamentamos lo ocurrido. El daño ocurrió en tránsito: "
            "podemos enviarte una reposición hoy mismo o devolverte el importe. "
            "¿Cuál prefieres?",
            fecha=fecha4_accion, autor=AutorComunicacion.HUMANO,
            usuario_id=oper_id,
        )
        c2 = _entrante(
            db, p4, "Prefiero la reposición, gracias por atender tan rápido.",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=c1.fecha + timedelta(hours=22),
        )
        _saliente(
            db, p4,
            "Perfecto Lucía, registramos la reposición: saldrá hoy y te "
            "compartiremos el número de guía. ¡Gracias por tu paciencia!",
            fecha=c2.fecha + timedelta(seconds=20),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.NEUTRO,
        )

        # ---------------------------------------------------------- 4.
        # HILO B — PD-2025-0005 · seguimiento normal de estado (sin escala)
        p5 = nuevos["PD-2025-0005"]
        c1 = _entrante(
            db, p5,
            "Buenas, ¿cómo va mi pedido PD-2025-0005? ¿Ya está en trámites de aduana?",
            intencion="ESTADO_PEDIDO", sentimiento=Sentimiento.NEUTRO,
            fecha=ahora - timedelta(days=1, hours=5),
        )
        _saliente(
            db, p5,
            f"Estimado Jorge Quispe, tu pedido PD-2025-0005 está en proceso "
            f"(importación en curso). Fecha prometida: "
            f"{p5.fecha_prometida.strftime('%d/%m/%Y')}. "
            "Ítems: 1x iPhone 15 128GB Azul. Te avisaremos en cada avance.",
            fecha=c1.fecha + timedelta(seconds=25),
            intencion="ESTADO_PEDIDO", sentimiento=Sentimiento.NEUTRO,
        )
        c2 = _entrante(
            db, p5, "Perfecto, muchas gracias por la información.",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=c1.fecha + timedelta(minutes=8),
        )
        _saliente(
            db, p5, "¡De nada, Jorge! Cualquier duda estamos por aquí.",
            fecha=c2.fecha + timedelta(seconds=20),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )

        # ---------------------------------------------------------- 5.
        # HILO C — PD-2025-0006 · conversación positiva (agradecimiento)
        p6 = nuevos["PD-2025-0006"]
        c1 = _entrante(
            db, p6,
            "Muchas gracias por mantenerme informada en cada paso; se nota el "
            "compromiso. ¡Todo excelente hasta ahora! 😊",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=ahora - timedelta(days=2, hours=1),
        )
        _saliente(
            db, p6,
            "¡Muchas gracias a ti, Andrea! Seguimos atentos para avisarte apenas "
            "haya novedades con tu pedido PD-2025-0006.",
            fecha=c1.fecha + timedelta(seconds=30),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )

        # ---------------------------------------------------------- 6.
        # HILO D — PD-2025-0007 · queja RECLAMO (demora) → caso RESUELTO
        p7 = nuevos["PD-2025-0007"]
        c1 = _entrante(
            db, p7,
            "Llevo casi dos semanas esperando mi MacBook y la fecha prometida ya "
            "se venció. Es inaceptable, exijo una respuesta de inmediato.",
            intencion="RECLAMO", sentimiento=Sentimiento.NEGATIVO,
            fecha=ahora - timedelta(days=1, hours=6),
        )
        fecha7_accion = c1.fecha + timedelta(minutes=40)
        fecha7_cierre = c1.fecha + timedelta(hours=1, minutes=15)
        caso7 = _caso(
            db, pedido=p7, prioridad=PrioridadCaso.ALTA,
            descripcion="Agente detectó RECLAMO. Escalar sin resolver.",
            apertura=c1.fecha, origen=c1,
            estado=EstadoCaso.RESUELTO, admin_id=admin_id, operador_id=oper_id,
            primera=fecha7_accion, cierre=fecha7_cierre,
        )
        c1.escalado, c1.caso_id = True, caso7.id
        _holding(db, p7, c1.fecha + timedelta(seconds=15), caso7)
        _saliente(
            db, p7,
            "Hola Camila, soy Renata de Polux Import. Lamentamos la demora: el "
            "proveedor retrasó el embarque. Confirmamos nueva fecha de entrega y "
            "bonificamos el envío por el inconveniente.",
            fecha=fecha7_accion, autor=AutorComunicacion.HUMANO,
            usuario_id=oper_id,
        )
        _entrante(
            db, p7, "Acepto la nueva fecha. Gracias por contestar rápido.",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=c1.fecha + timedelta(hours=1, minutes=5),
        )
        _saliente(
            db, p7,
            f"Listo, Camila: caso #{caso7.id} cerrado y actualizado en tu pedido. "
            "Quedamos atentos ante cualquier duda.",
            fecha=fecha7_cierre, autor=AutorComunicacion.HUMANO,
            usuario_id=oper_id,
        )

        # ---------------------------------------------------------- 7.
        # HILO E — PD-2025-0008 · consulta de retraso NEUTRO (sin escala)
        p8 = nuevos["PD-2025-0008"]
        c1 = _entrante(
            db, p8,
            "Hola, ¿mi pedido sigue en la fecha prometida o se volvió a mover?",
            intencion="RETRASO", sentimiento=Sentimiento.NEUTRO,
            fecha=ahora - timedelta(days=1, hours=3),
        )
        _saliente(
            db, p8,
            f"Estimado Renzo Torres, tu pedido PD-2025-0008 está en proceso y sin "
            f"retrasos pendientes. Fecha prometida: "
            f"{p8.fecha_prometida.strftime('%d/%m/%Y')}. Te avisaremos apenas haya "
            "movimientos de importación.",
            fecha=c1.fecha + timedelta(seconds=30),
            intencion="RETRASO", sentimiento=Sentimiento.NEUTRO,
        )
        c2 = _entrante(
            db, p8, "Ok, perfecto. ¡Gracias!",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=c1.fecha + timedelta(minutes=6),
        )
        _saliente(
            db, p8, "¡Gracias a ti, Renzo! Seguimos en contacto.",
            fecha=c2.fecha + timedelta(seconds=15),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )

        # ---------------------------------------------------------- 8.
        # HILO F — PD-2025-0009 · conversación positiva + consulta breve
        p9 = nuevos["PD-2025-0009"]
        c1 = _entrante(
            db, p9,
            "Excelente servicio, ya le recomendé a mi hermana. ¿También hacen "
            "envíos a Arequipa?",
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
            fecha=ahora - timedelta(days=1, hours=1),
        )
        _saliente(
            db, p9,
            "¡Gracias por la recomendación, Valeria! Sí, enviamos a todo el Perú; "
            "coordinamos la entrega una vez que tu pedido PD-2025-0009 esté listo.",
            fecha=c1.fecha + timedelta(seconds=30),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )
        c2 = _entrante(
            db, p9, "Genial, entonces espero su aviso 😊",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=c1.fecha + timedelta(minutes=5),
        )
        _saliente(
            db, p9, "Cualquier cosa nos escribes, ¡saludos!",
            fecha=c2.fecha + timedelta(seconds=15),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )

        # ---------------------------------------------------------- 9.
        # HILO G — PD-2025-0010 · queja RECLAMO (cobro) → caso ABIERTO aún
        p10 = nuevos["PD-2025-0010"]
        c1 = _entrante(
            db, p10,
            "Me cobraron S/ 150 de más en mi segundo pago. Quiero una explicación "
            "y la devolución de inmediato.",
            intencion="RECLAMO", sentimiento=Sentimiento.NEGATIVO,
            fecha=ahora - timedelta(days=1, hours=4),
        )
        caso10 = _caso(
            db, pedido=p10, prioridad=PrioridadCaso.ALTA,
            descripcion="Agente detectó RECLAMO. Escalar sin resolver.",
            apertura=c1.fecha, origen=c1,
            estado=EstadoCaso.ABIERTO, admin_id=admin_id, operador_id=oper_id,
        )
        c1.escalado, c1.caso_id = True, caso10.id
        _holding(db, p10, c1.fecha + timedelta(seconds=15), caso10)
        # (sin respuesta humana todavía: muestra un caso en espera de asesor)

        # ---------------------------------------------------------- 10.
        # Cierres de los 3 pedidos demo (los tres siguen siendo conversaciones)
        # PD-2025-0001 — seguimiento que termina en agradecimiento
        c1 = _entrante(
            db, p1, "¡Muchas gracias! Entonces me queda esperar el envío 🙌",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=ahora - timedelta(minutes=30),
        )
        _saliente(
            db, p1,
            "¡De nada, María! Te avisaremos apenas tu pedido PD-2025-0001 salga "
            "hacia tu domicilio. 😊",
            fecha=c1.fecha + timedelta(seconds=20),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )

        # PD-2025-0002 — la queja demo (caso #1) cerró en satisfacción
        c1 = _entrante(
            db, p2, "Gracias, ayer me contactaron y resolvieron mi caso. Impecable "
                    "el servicio.",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=ahora - timedelta(minutes=15),
        )
        _saliente(
            db, p2,
            "Me alegra saberlo, María. Tu caso quedó resuelto y el pedido "
            "PD-2025-0002 continúa en proceso. ¡Quedamos atentos!",
            fecha=c1.fecha + timedelta(seconds=20),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )

        # PD-2025-0003 — el agente responde al retraso y un asesor toma el caso
        ultima = db.scalar(
            select(Comunicacion)
            .where(Comunicacion.pedido_id == p3.id)
            .order_by(Comunicacion.fecha.desc())
            .limit(1)
        )
        base = _antes(
            (ultima.fecha if ultima else ahora) + timedelta(minutes=2),
            ahora - timedelta(minutes=20),
        )
        caso2 = db.scalar(
            select(CasoEscalamiento).where(CasoEscalamiento.id == 2)
        )
        _saliente(
            db, p3,
            f"Estimado Carlos Mendoza, tu pedido PD-2025-0003 está en proceso: la "
            f"importación avanza y el trámite aduanero está en curso. Fecha "
            f"prometida: {p3.fecha_prometida.strftime('%d/%m/%Y')}. Te avisamos en "
            "cuanto salga de aduana.",
            fecha=base, intencion="RETRASO", sentimiento=Sentimiento.NEUTRO,
        )
        c1 = _entrante(
            db, p3, "Entiendo. ¿Y cómo va el caso que se abrió por el retraso?",
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.NEUTRO,
            fecha=base + timedelta(minutes=2),
        )
        _saliente(
            db, p3,
            "Tu caso por retraso crítico ya está siendo atendido; una asesora te "
            "contactará en unos minutos.",
            fecha=c1.fecha + timedelta(seconds=20),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.NEUTRO,
        )
        if caso2 is not None and caso2.fecha_primera_accion is None:
            caso2.fecha_primera_accion = base + timedelta(minutes=9)
            caso2.estado = EstadoCaso.EN_PROCESO
            caso2.responsable_id = oper_id
            caso2.updated_by_id = admin_id
        _saliente(
            db, p3,
            "Hola Carlos, soy Renata del equipo Polux Import. Estoy gestionando tu "
            "caso por retraso: el embarque cruza revisión aduanera y te confirmo "
            "novedades hoy mismo.",
            fecha=base + timedelta(minutes=9), autor=AutorComunicacion.HUMANO,
            usuario_id=oper_id,
        )
        c2 = _entrante(
            db, p3, "Perfecto, muchas gracias.",
            intencion="OTRO", sentimiento=Sentimiento.POSITIVO,
            fecha=base + timedelta(minutes=12),
        )
        _saliente(
            db, p3, "Cualquier avance te lo compartimos por aquí, Carlos. ¡Saludos!",
            fecha=c2.fecha + timedelta(seconds=15),
            intencion="CONSULTA_GENERAL", sentimiento=Sentimiento.POSITIVO,
        )

        db.commit()

        # ---------------------------------------------------------- 11.
        # Hechos dimensionales (KPI) — insert-only e idempotente.
        facts = FactSyncService(db).sync_all()

        comms = db.scalar(select(Comunicacion.id).limit(1)) is not None
        total_com = len(db.scalars(select(Comunicacion.id)).all())
        total_casos = len(db.scalars(select(CasoEscalamiento.id)).all())
        total_pedidos = len(db.scalars(select(Pedido.id)).all())
        print(f"[g3] OK — pedidos={total_pedidos} comunicaciones={total_com} "
              f"casos={total_casos} comms_presentes={comms}")
        print(f"[g3] fact_sync: {facts}")
        print("[g3] Verifica: GET /api/v1/agent/chats (10 conversaciones) y "
              "GET /api/v1/dashboard/resumen")
    finally:
        db.close()


if __name__ == "__main__":
    run()

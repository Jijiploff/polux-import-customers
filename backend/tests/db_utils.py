"""Utilidades de limpieza de BD para tests.

El orden importa: hay una circularidad `comunicacion.caso_id ↔
caso_escalamiento.comunicacion_origen_id`, y `alerta` referencia
`pedido_item` e `item_hito`. Borrar en el orden equivocado revienta con
IntegrityError 547 en el teardown (pytest lo marca como ERROR/FAILED).
"""
from sqlalchemy import delete, select, update

from app.models import (
    Alerta,
    CasoEscalamiento,
    CasoTelegramNotificacion,
    Cliente,
    Comunicacion,
    Conformidad,
    Entrega,
    EntregaItem,
    EstadoHito,
    EstadoIngreso,
    EstadoItem,
    EstadoPedido,
    FactComunicacion,
    FactEscalamiento,
    FactEntrega,
    FactHitoPedido,
    FactImprevisto,
    HitoCatalogo,
    Imprevisto,
    ItemHito,
    ModalidadEntrega,
    OrigenItem,
    Pedido,
    PedidoItem,
    UsuarioCasoActivo,
)


def cleanup_pedido(db, pedido_id: int) -> None:
    """Borra en orden seguro todo lo que un test pudo crear para un pedido.

    También elimina el cliente si queda sin pedidos (evita huérfanos con
    teléfono compartido que confunden el matching del webhook de WhatsApp).
    """
    from app.models import Cliente, Contrato

    cliente_id = db.scalar(
        select(Pedido.cliente_id).where(Pedido.id == pedido_id)
    )
    # 1) Romper la circularidad comunicacion.caso_id → caso_escalamiento
    db.execute(
        update(Comunicacion)
        .where(
            Comunicacion.pedido_id == pedido_id,
            Comunicacion.caso_id.is_not(None),
        )
        .values(caso_id=None)
    )
    # 2) Alertas (referencian pedido_item e item_hito)
    db.execute(delete(Alerta).where(Alerta.pedido_id == pedido_id))
    # 3) Hechos (sin FK, por higiene)
    for fact in (
        FactHitoPedido, FactComunicacion, FactEscalamiento,
        FactImprevisto, FactEntrega,
    ):
        db.execute(delete(fact).where(fact.pedido_id == pedido_id))
    # 4) Entregas: conformidad → entrega_item → entrega
    db.execute(delete(Conformidad).where(Conformidad.entrega_item_id.in_(
        select(EntregaItem.id).where(EntregaItem.entrega_id.in_(
            select(Entrega.id).where(Entrega.pedido_id == pedido_id)
        ))
    )))
    db.execute(delete(EntregaItem).where(EntregaItem.entrega_id.in_(
        select(Entrega.id).where(Entrega.pedido_id == pedido_id)
    )))
    db.execute(delete(Entrega).where(Entrega.pedido_id == pedido_id))
    # 5) Casos e imprevistos (referencian comunicacion/pedido_item)
    db.execute(delete(CasoTelegramNotificacion).where(
        CasoTelegramNotificacion.caso_id.in_(
            select(CasoEscalamiento.id).where(CasoEscalamiento.pedido_id == pedido_id)
        )
    ))
    db.execute(delete(UsuarioCasoActivo).where(
        UsuarioCasoActivo.caso_id.in_(
            select(CasoEscalamiento.id).where(CasoEscalamiento.pedido_id == pedido_id)
        )
    ))
    db.execute(delete(CasoEscalamiento).where(
        CasoEscalamiento.pedido_id == pedido_id
    ))
    db.execute(delete(Imprevisto).where(Imprevisto.pedido_id == pedido_id))
    # 6) Comunicaciones
    db.execute(delete(Comunicacion).where(Comunicacion.pedido_id == pedido_id))
    # 7) Hitos e ítems
    db.execute(delete(ItemHito).where(ItemHito.pedido_item_id.in_(
        select(PedidoItem.id).where(PedidoItem.pedido_id == pedido_id)
    )))
    db.execute(delete(PedidoItem).where(PedidoItem.pedido_id == pedido_id))
    # 8) El pedido
    db.execute(delete(Pedido).where(Pedido.id == pedido_id))
    # 9) Cliente huérfano (sin pedidos ni contratos) — no dejar residuos
    if cliente_id is not None:
        quedan = db.scalar(
            select(Pedido.id).where(Pedido.cliente_id == cliente_id).limit(1)
        )
        contrato = db.scalar(
            select(Contrato.id).where(Contrato.cliente_id == cliente_id).limit(1)
        )
        if quedan is None and contrato is None:
            db.execute(delete(Cliente).where(Cliente.id == cliente_id))
    db.commit()


def crear_pedido_listo(db, *, con_hito: bool = False):
    """Crea un pedido de prueba fresco con un ítem LISTO_PARA_ENTREGA.

    Evita que los tests operen sobre los pedidos demo (que están cerrados
    o en estados que devuelven 409) ni sobre residuos de corridas previas.
    Con ``con_hito=True`` agrega un ``ItemHito`` PENDIENTE al primer hito
    del catálogo para el origen del ítem.
    """
    from datetime import datetime, timedelta
    import uuid

    suf = uuid.uuid4().hex[:6]
    cli = Cliente(
        nombre=f"T{suf}", consentimiento_datos=True,
        consentimiento_fecha=datetime.utcnow(),
    )
    db.add(cli)
    db.flush()
    ped = Pedido(
        codigo=f"PD-TEST-{suf}", cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.EN_PROCESO,
        fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow() + timedelta(days=7),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped)
    db.flush()
    item = PedidoItem(
        pedido_id=ped.id, descripcion_producto="Ítem de prueba",
        cantidad=1, origen=OrigenItem.STOCK_TRUJILLO,
        estado=EstadoItem.LISTO_PARA_ENTREGA,
    )
    db.add(item)
    db.flush()
    ih = None
    if con_hito:
        hito = db.scalar(
            select(HitoCatalogo)
            .where(HitoCatalogo.origen == OrigenItem.STOCK_TRUJILLO)
            .order_by(HitoCatalogo.orden)
        )
        if hito is None:
            hito = HitoCatalogo(
                codigo="STOCK_PREPARACION", nombre="Preparación",
                origen=OrigenItem.STOCK_TRUJILLO, orden=1, activo=True,
            )
            db.add(hito)
            db.flush()
        ih = ItemHito(
            pedido_item_id=item.id, hito_id=hito.id,
            fecha_prevista=datetime.utcnow() + timedelta(days=1),
            estado=EstadoHito.PENDIENTE,
        )
        db.add(ih)
    db.commit()
    db.refresh(ped)
    db.refresh(item)
    return ped, item, ih

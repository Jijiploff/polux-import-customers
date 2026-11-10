"""Ciclo completo end-to-end del pedido — acepción §12 del plan.

Bienvenida → hitos completados → imprevisto → escalamiento → entrega
completa con conformidad → cierre del pedido → fact_entrega disponible.
"""
from datetime import datetime, timedelta
import uuid

import pytest
from sqlalchemy import delete, select

from app.db.session import SessionLocal
from app.models import (
    CasoEscalamiento, Cliente, Comunicacion, Conformidad, Entrega, EntregaItem,
    EstadoEntrega, EstadoImprevisto, EstadoIngreso, EstadoItem, EstadoPedido,
    FactEntrega, HitoCatalogo, Imprevisto, ItemHito, ModalidadEntrega, OrigenItem,
    Pedido, PedidoItem, ResultadoConformidad, SlaHito, TipoEntrega, TipoImprevisto,
)
from app.services.entrega_service import completar_entrega, crear_entrega
from app.services.fact_sync_service import FactSyncService
from app.services.hito_service import marcar_completado
from app.services.rule_engine import RuleEngine
from app.schemas.entrega import ConformidadItemIn, EntregaCreate


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _mk(db):
    suf = uuid.uuid4().hex[:6]
    cli = Cliente(nombre=f"Cliente {suf}", telefono_whatsapp=f"+5199{suf}",
                  consentimiento_datos=True, consentimiento_fecha=datetime.utcnow())
    db.add(cli); db.flush()
    ped = Pedido(
        codigo=f"PD-E2E-{suf}", cliente_id=cli.id,
        estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
        estado_actual=EstadoPedido.RECIBIDO,
        fecha_ingreso=datetime.utcnow(),
        fecha_prometida=datetime.utcnow() + timedelta(days=7),
        modalidad_entrega=ModalidadEntrega.DOMICILIO,
    )
    db.add(ped); db.flush()
    item = PedidoItem(
        pedido_id=ped.id, descripcion_producto="iPhone E2E", cantidad=1,
        origen=OrigenItem.STOCK_TRUJILLO, estado=EstadoItem.PENDIENTE,
    )
    db.add(item); db.flush()

    hitos = db.scalars(
        select(HitoCatalogo).where(HitoCatalogo.origen == OrigenItem.STOCK_TRUJILLO)
        .order_by(HitoCatalogo.orden)
    ).all()
    prev = ped.fecha_ingreso
    for h in hitos:
        sla = db.scalar(select(SlaHito).where(SlaHito.hito_id == h.id))
        prev = prev + timedelta(days=(sla.dias_maximos if sla else 1))
        db.add(ItemHito(pedido_item_id=item.id, hito_id=h.id,
                        fecha_prevista=prev, estado="PENDIENTE"))
    db.commit()
    db.refresh(ped); db.refresh(item)
    return cli, ped, item


def _cleanup(db, pedido_id):
    from tests.db_utils import cleanup_pedido
    cleanup_pedido(db, pedido_id)


def test_e2e_flujo_completo(db):
    cli, ped, item = _mk(db)
    try:
        # 1) Motor de reglas: bienvenida
        RuleEngine(db).run_all()
        bienvenidas = db.scalars(
            select(Comunicacion).where(
                Comunicacion.pedido_id == ped.id,
                Comunicacion.direccion == "SALIENTE",
            )
        ).all()
        assert len(bienvenidas) >= 1, "Debe enviarse bienvenida"

        # 2) Completar hitos uno a uno
        hitos = db.scalars(
            select(ItemHito).where(ItemHito.pedido_item_id == item.id)
            .order_by(ItemHito.id)
        ).all()
        for h in hitos:
            marcar_completado(db, h.id, fecha_real=datetime.utcnow(), usuario_id=None)
        db.refresh(item)
        assert item.estado == EstadoItem.LISTO_PARA_ENTREGA

        # 3) Motor de reglas: aviso de hitos consolidado y paso a LISTO_PARA_ENTREGA
        RuleEngine(db).run_all()
        db.refresh(ped)
        # El motor puede dejarlo en LISTO_PARA_ENTREGA o EN_COORDINACION tras notificar.
        assert ped.estado_actual in (EstadoPedido.LISTO_PARA_ENTREGA,
                                     EstadoPedido.EN_COORDINACION)

        # 4) Entrega completa con conformidad
        entrega = crear_entrega(db, EntregaCreate(
            pedido_id=ped.id, tipo=TipoEntrega.COMPLETA,
            modalidad=ModalidadEntrega.DOMICILIO,
            fecha_programada=datetime.utcnow(),
        ), usuario_id=None)

        confs = [ConformidadItemIn(
            pedido_item_id=item.id,
            checklist_caja_sellada=True, checklist_modelo_ok=True,
            checklist_color_ok=True, checklist_capacidad_ok=True,
            checklist_imei_ok=True, checklist_accesorios_ok=True,
            resultado=ResultadoConformidad.CONFORME,
        )]
        completar_entrega(db, entrega.id, fecha_real=datetime.utcnow(),
                          conformidades=confs, usuario_id=None)

        db.refresh(ped); db.refresh(item)
        assert item.estado == EstadoItem.ENTREGADO
        assert ped.estado_actual == EstadoPedido.CERRADO

        # 5) Sync de hechos y verificación del fact_entrega
        FactSyncService(db).sync_all()
        f = db.scalar(select(FactEntrega).where(FactEntrega.pedido_id == ped.id))
        assert f is not None
        assert f.tipo == "COMPLETA"
        assert f.con_observaciones is False

        # 6) KPIs responden tras el flujo (no rompen con datos nuevos)
        from app.services.kpi_service import KpiService
        ksvc = KpiService(db)
        for codigo in ["FREQ_ACTUALIZACION_CLIENTE", "ENTREGAS_A_TIEMPO",
                       "ENTREGAS_SIN_OBSERVACIONES"]:
            serie = ksvc.get_serie(codigo, desde=datetime.utcnow().date() - timedelta(days=30),
                                   hasta=datetime.utcnow().date(), granularidad="dia")
            assert "serie" in serie
    finally:
        _cleanup(db, ped.id)


def test_e2e_imprevisto_y_escalamiento(db):
    cli, ped, item = _mk(db)
    try:
        # Crear un imprevisto → motor de reglas debe crear alerta + caso
        db.add(Imprevisto(
            pedido_id=ped.id, pedido_item_id=item.id,
            tipo=TipoImprevisto.ADUANERO,
            descripcion="Retenido en aduana",
            fecha_deteccion=datetime.utcnow(),
            estado=EstadoImprevisto.ABIERTO,
        ))
        db.commit()
        RuleEngine(db).run_all()

        caso = db.scalar(select(CasoEscalamiento).where(
            CasoEscalamiento.pedido_id == ped.id,
            CasoEscalamiento.motivo == "IMPREVISTO",
        ))
        assert caso is not None

        # Cerrar imprevisto y verificar que sigue trazable
        imp = db.scalar(select(Imprevisto).where(Imprevisto.pedido_id == ped.id))
        imp.estado = EstadoImprevisto.RESUELTO
        imp.fecha_resolucion = datetime.utcnow()
        imp.resolucion = "Documentación entregada"
        db.commit()
        assert imp.fecha_resolucion is not None
    finally:
        _cleanup(db, ped.id)
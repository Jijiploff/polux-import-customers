"""Smoke tests de Fase 1: el esquema existe y las restricciones inviolables actúan."""
from datetime import datetime

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal, engine
from app.models import (
    Cliente,
    Entrega,
    ModalidadEntrega,
    Pedido,
    TipoEntrega,
    EstadoIngreso,
)


def test_tables_exist():
    insp = inspect(engine)
    tablas = set(insp.get_table_names())
    requeridas = {
        "pedido", "pedido_item", "hito_catalogo", "sla_hito", "item_hito",
        "plantilla_mensaje", "comunicacion", "alerta", "imprevisto",
        "caso_escalamiento", "entrega", "entrega_item", "conformidad",
        "regla_negocio", "usuario", "rol", "usuario_rol",
        "cliente", "producto", "contrato",
        "dim_tiempo", "dim_canal", "dim_producto", "dim_hito",
        "dim_tipo_imprevisto", "dim_kpi",
        "fact_hito_pedido", "fact_comunicacion", "fact_escalamiento",
        "fact_imprevisto", "fact_entrega",
    }
    faltantes = requeridas - tablas
    assert not faltantes, f"Faltan tablas: {faltantes}"


def test_kpi_views_exist():
    insp = inspect(engine)
    vistas = set(insp.get_view_names())
    requeridas = {
        "vw_kpi_actualizacion_cliente",
        "vw_kpi_resolucion_automatica",
        "vw_kpi_tiempo_respuesta_escalados",
        "vw_kpi_resolucion_imprevistos",
        "vw_kpi_entregas_a_tiempo",
        "vw_kpi_entregas_sin_observaciones",
        "vw_kpi_entregas_parciales",
    }
    faltantes = requeridas - vistas
    assert not faltantes, f"Faltan vistas: {faltantes}"


def test_entrega_parcial_sin_autorizacion_falla():
    """Regla inviolable: entrega parcial sin autorización → CHECK de BD."""
    db = SessionLocal()
    try:
        cli = Cliente(nombre="Test Cliente")
        db.add(cli)
        db.flush()
        ped = Pedido(
            codigo="PD-TEST-PARCIAL", cliente_id=cli.id,
            estado_ingreso=EstadoIngreso.PRIMER_PAGO_VERIFICADO,
            fecha_ingreso=datetime.utcnow(),
            fecha_prometida=datetime.utcnow(),
            modalidad_entrega=ModalidadEntrega.DOMICILIO,
        )
        db.add(ped)
        db.flush()
        db.add(Entrega(
            pedido_id=ped.id, tipo=TipoEntrega.PARCIAL,
            modalidad=ModalidadEntrega.DOMICILIO,
            fecha_programada=datetime.utcnow(),
        ))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()
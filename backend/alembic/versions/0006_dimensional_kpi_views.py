"""Calcula las vistas de KPI desde el modelo dimensional.

Revision ID: 0006_dimensional_kpi_views
Revises: 0005_comunicacion_wamid_filtered
Create Date: 2026-11-10
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0006_dimensional_kpi_views"
down_revision: Union[str, None] = "0005_comunicacion_wamid_filtered"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEWS_UP = [
    """
    CREATE OR ALTER VIEW vw_kpi_actualizacion_cliente AS
    SELECT COUNT(*) AS hitos_completados,
           SUM(CASE WHEN f.notificado_oportuno = 1 THEN 1 ELSE 0 END)
               AS hitos_notificados_oportunos,
           CAST(CASE WHEN COUNT(*) = 0 THEN NULL
                     ELSE 100.0 * SUM(CASE WHEN f.notificado_oportuno = 1
                                           THEN 1 ELSE 0 END) / COUNT(*)
                END AS DECIMAL(6,2)) AS kpi_porcentaje
    FROM fact_hito_pedido f
    WHERE f.completado = 1
    """,
    """
    CREATE OR ALTER VIEW vw_kpi_resolucion_automatica AS
    SELECT COUNT(*) AS total_consultas,
           SUM(CASE WHEN f.escalado = 0 THEN 1 ELSE 0 END)
               AS resueltas_automaticamente,
           CAST(CASE WHEN COUNT(*) = 0 THEN NULL
                     ELSE 100.0 * SUM(CASE WHEN f.escalado = 0
                                           THEN 1 ELSE 0 END) / COUNT(*)
                END AS DECIMAL(6,2)) AS kpi_porcentaje
    FROM fact_comunicacion f
    WHERE f.direccion = 'ENTRANTE'
      AND f.autor = 'CLIENTE'
    """,
    """
    CREATE OR ALTER VIEW vw_kpi_tiempo_respuesta_escalados AS
    SELECT COUNT(*) AS casos_con_respuesta,
           CAST(AVG(f.horas_respuesta) AS DECIMAL(10,2))
               AS kpi_horas_promedio
    FROM fact_escalamiento f
    WHERE f.horas_respuesta IS NOT NULL
    """,
    """
    CREATE OR ALTER VIEW vw_kpi_resolucion_imprevistos AS
    SELECT COALESCE(t.codigo, 'SIN_TIPO') AS tipo,
           COUNT(*) AS imprevistos_resueltos,
           CAST(AVG(f.dias_resolucion) AS DECIMAL(10,2))
               AS kpi_dias_promedio
    FROM fact_imprevisto f
    LEFT JOIN dim_tipo_imprevisto t ON t.id = f.tipo_id
    WHERE f.dias_resolucion IS NOT NULL
    GROUP BY COALESCE(t.codigo, 'SIN_TIPO')
    """,
    """
    CREATE OR ALTER VIEW vw_kpi_entregas_a_tiempo AS
    WITH entregas_completas AS (
        SELECT f.pedido_id, MAX(CASE WHEN f.a_tiempo = 1 THEN 1 ELSE 0 END)
                                   AS a_tiempo
        FROM fact_entrega f
        WHERE f.tipo = 'COMPLETA'
        GROUP BY f.pedido_id
    )
    SELECT COUNT(*) AS pedidos_entregados,
           SUM(a_tiempo) AS pedidos_a_tiempo,
           CAST(CASE WHEN COUNT(*) = 0 THEN NULL
                     ELSE 100.0 * SUM(a_tiempo) / COUNT(*)
                END AS DECIMAL(6,2)) AS kpi_porcentaje
    FROM entregas_completas
    """,
    """
    CREATE OR ALTER VIEW vw_kpi_entregas_sin_observaciones AS
    WITH pedidos_entregados AS (
        SELECT f.pedido_id
        FROM fact_entrega f
        GROUP BY f.pedido_id
    ),
    pedidos_con_observacion AS (
        SELECT f.pedido_id
        FROM fact_entrega f
        WHERE f.con_observaciones = 1
        GROUP BY f.pedido_id
    )
    SELECT (SELECT COUNT(*) FROM pedidos_entregados) AS pedidos_entregados,
           (SELECT COUNT(*) FROM pedidos_entregados p
            WHERE NOT EXISTS (
                SELECT 1 FROM pedidos_con_observacion o
                WHERE o.pedido_id = p.pedido_id
            )) AS pedidos_sin_observaciones,
           CAST(CASE WHEN (SELECT COUNT(*) FROM pedidos_entregados) = 0 THEN NULL
                     ELSE 100.0 * (SELECT COUNT(*) FROM pedidos_entregados p
                                   WHERE NOT EXISTS (
                                       SELECT 1 FROM pedidos_con_observacion o
                                       WHERE o.pedido_id = p.pedido_id
                                   ))
                          / (SELECT COUNT(*) FROM pedidos_entregados)
                END AS DECIMAL(6,2)) AS kpi_porcentaje
    """,
    """
    CREATE OR ALTER VIEW vw_kpi_entregas_parciales AS
    WITH pedidos_entregados AS (
        SELECT f.pedido_id
        FROM fact_entrega f
        GROUP BY f.pedido_id
    ),
    pedidos_con_parcial AS (
        SELECT f.pedido_id
        FROM fact_entrega f
        WHERE f.tipo = 'PARCIAL'
        GROUP BY f.pedido_id
    )
    SELECT (SELECT COUNT(*) FROM pedidos_entregados) AS pedidos_entregados,
           (SELECT COUNT(*) FROM pedidos_entregados p
            WHERE EXISTS (
                SELECT 1 FROM pedidos_con_parcial x
                WHERE x.pedido_id = p.pedido_id
            )) AS pedidos_con_parcial,
           CAST(CASE WHEN (SELECT COUNT(*) FROM pedidos_entregados) = 0 THEN NULL
                     ELSE 100.0 * (SELECT COUNT(*) FROM pedidos_entregados p
                                   WHERE EXISTS (
                                       SELECT 1 FROM pedidos_con_parcial x
                                       WHERE x.pedido_id = p.pedido_id
                                   ))
                          / (SELECT COUNT(*) FROM pedidos_entregados)
                END AS DECIMAL(6,2)) AS kpi_porcentaje
    """,
]


def upgrade() -> None:
    for ddl in VIEWS_UP:
        op.execute(ddl)


def downgrade() -> None:
    # La revisión anterior también expone las mismas vistas; restaurarla
    # mantiene el downgrade reversible sin eliminar el dashboard.
    from importlib.util import module_from_spec, spec_from_file_location
    from pathlib import Path

    previous = Path(__file__).with_name("0002_kpi_views.py")
    spec = spec_from_file_location("previous_kpi_views", previous)
    if spec is None or spec.loader is None:
        raise RuntimeError("No se pudo cargar la revisión anterior de vistas KPI")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    for ddl in module.VIEWS_UP:
        op.execute(ddl)

"""Vistas SQL para los 6 KPIs del dashboard + indicador complementario.

Revision ID: 0002_kpi_views
Revises: 0001_initial_schema
Create Date: 2025-01-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002_kpi_views"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


VIEWS_UP = [
    # KPI 1 — Frecuencia de actualización al cliente
    """
    CREATE OR ALTER VIEW vw_kpi_actualizacion_cliente AS
    SELECT
        COUNT(*) AS hitos_completados,
        SUM(CASE WHEN ih.fecha_notificacion IS NOT NULL
                  AND DATEDIFF(HOUR, ih.fecha_real, ih.fecha_notificacion) <= 2
                 THEN 1 ELSE 0 END) AS hitos_notificados_oportunos,
        CAST(
            CASE WHEN COUNT(*) = 0 THEN NULL
                 ELSE 100.0 * SUM(CASE WHEN ih.fecha_notificacion IS NOT NULL
                                        AND DATEDIFF(HOUR, ih.fecha_real, ih.fecha_notificacion) <= 2
                                       THEN 1 ELSE 0 END) / COUNT(*)
            END AS DECIMAL(6,2)
        ) AS kpi_porcentaje
    FROM item_hito ih
    WHERE ih.estado = 'COMPLETADO'
    """,
    # KPI 2 — Tasa de resolución automática (aprox. v1: por comunicación entrante marcada no escalada)
    """
    CREATE OR ALTER VIEW vw_kpi_resolucion_automatica AS
    SELECT
        COUNT(*) AS total_consultas,
        SUM(CASE WHEN c.escalado = 0 THEN 1 ELSE 0 END) AS resueltas_automaticamente,
        CAST(
            CASE WHEN COUNT(*) = 0 THEN NULL
                 ELSE 100.0 * SUM(CASE WHEN c.escalado = 0 THEN 1 ELSE 0 END) / COUNT(*)
            END AS DECIMAL(6,2)
        ) AS kpi_porcentaje
    FROM comunicacion c
    WHERE c.direccion = 'ENTRANTE'
      AND c.autor = 'CLIENTE'
    """,
    # KPI 3 — Tiempo de respuesta a escalados (horas promedio, casos con primera acción)
    """
    CREATE OR ALTER VIEW vw_kpi_tiempo_respuesta_escalados AS
    SELECT
        COUNT(*) AS casos_con_respuesta,
        CAST(
            CASE WHEN COUNT(*) = 0 THEN NULL
                 ELSE AVG(CAST(DATEDIFF(MINUTE, ce.fecha_apertura, ce.fecha_primera_accion) AS FLOAT) / 60.0)
            END AS DECIMAL(10,2)
        ) AS kpi_horas_promedio
    FROM caso_escalamiento ce
    WHERE ce.fecha_primera_accion IS NOT NULL
    """,
    # KPI 4 — Tiempo de resolución de imprevistos (días promedio por tipo)
    """
    CREATE OR ALTER VIEW vw_kpi_resolucion_imprevistos AS
    SELECT
        i.tipo AS tipo,
        COUNT(*) AS imprevistos_resueltos,
        CAST(
            CASE WHEN COUNT(*) = 0 THEN NULL
                 ELSE AVG(CAST(DATEDIFF(MINUTE, i.fecha_deteccion, i.fecha_resolucion) AS FLOAT) / 1440.0)
            END AS DECIMAL(10,2)
        ) AS kpi_dias_promedio
    FROM imprevisto i
    WHERE i.fecha_resolucion IS NOT NULL
    GROUP BY i.tipo
    """,
    # KPI 5 — Entregas a tiempo
    """
    CREATE OR ALTER VIEW vw_kpi_entregas_a_tiempo AS
    WITH pedidos_entregados AS (
        SELECT p.id AS pedido_id, p.fecha_prometida,
               MAX(e.fecha_real) AS fecha_completada,
               MAX(CASE WHEN e.tipo = 'PARCIAL' THEN 1 ELSE 0 END) AS tiene_parcial
        FROM pedido p
        INNER JOIN entrega e ON e.pedido_id = p.id AND e.estado = 'ENTREGADA'
        GROUP BY p.id, p.fecha_prometida
    )
    SELECT
        COUNT(*) AS pedidos_entregados,
        SUM(CASE WHEN fecha_completada <= fecha_prometida THEN 1 ELSE 0 END) AS pedidos_a_tiempo,
        CAST(
            CASE WHEN COUNT(*) = 0 THEN NULL
                 ELSE 100.0 * SUM(CASE WHEN fecha_completada <= fecha_prometida THEN 1 ELSE 0 END) / COUNT(*)
            END AS DECIMAL(6,2)
        ) AS kpi_porcentaje
    FROM pedidos_entregados
    """,
    # KPI 6 — Entregas confirmadas sin observaciones
    """
    CREATE OR ALTER VIEW vw_kpi_entregas_sin_observaciones AS
    WITH pedidos_entregados AS (
        SELECT DISTINCT e.pedido_id
        FROM entrega e
        WHERE e.estado = 'ENTREGADA'
    ),
    pedidos_con_observacion AS (
        SELECT DISTINCT e.pedido_id
        FROM entrega e
        INNER JOIN entrega_item ei ON ei.entrega_id = e.id
        INNER JOIN conformidad c ON c.entrega_item_id = ei.id
        WHERE e.estado = 'ENTREGADA'
          AND c.resultado = 'CON_OBSERVACIONES'
    ),
    pedidos_sin_conformidad AS (
        SELECT DISTINCT e.pedido_id
        FROM entrega e
        INNER JOIN entrega_item ei ON ei.entrega_id = e.id
        LEFT JOIN conformidad c ON c.entrega_item_id = ei.id
        WHERE e.estado = 'ENTREGADA' AND c.id IS NULL
    )
    SELECT
        (SELECT COUNT(*) FROM pedidos_entregados) AS pedidos_entregados,
        (SELECT COUNT(*) FROM pedidos_entregados pe
            WHERE pe.pedido_id NOT IN (SELECT pedido_id FROM pedidos_con_observacion)
              AND pe.pedido_id NOT IN (SELECT pedido_id FROM pedidos_sin_conformidad)) AS pedidos_sin_observaciones,
        CAST(
            CASE WHEN (SELECT COUNT(*) FROM pedidos_entregados) = 0 THEN NULL
                 ELSE 100.0 * (SELECT COUNT(*) FROM pedidos_entregados pe
                                WHERE pe.pedido_id NOT IN (SELECT pedido_id FROM pedidos_con_observacion)
                                  AND pe.pedido_id NOT IN (SELECT pedido_id FROM pedidos_sin_conformidad))
                      / (SELECT COUNT(*) FROM pedidos_entregados)
            END AS DECIMAL(6,2)
        ) AS kpi_porcentaje
    """,
    # Complementario — % pedidos con entrega parcial
    """
    CREATE OR ALTER VIEW vw_kpi_entregas_parciales AS
    WITH pedidos_con_parcial AS (
        SELECT DISTINCT pedido_id FROM entrega WHERE tipo = 'PARCIAL'
    ),
    pedidos_entregados AS (
        SELECT DISTINCT pedido_id FROM entrega WHERE estado = 'ENTREGADA'
    )
    SELECT
        (SELECT COUNT(*) FROM pedidos_entregados) AS pedidos_entregados,
        (SELECT COUNT(*) FROM pedidos_entregados pe
            WHERE pe.pedido_id IN (SELECT pedido_id FROM pedidos_con_parcial)) AS pedidos_con_parcial,
        CAST(
            CASE WHEN (SELECT COUNT(*) FROM pedidos_entregados) = 0 THEN NULL
                 ELSE 100.0 * (SELECT COUNT(*) FROM pedidos_entregados pe
                                WHERE pe.pedido_id IN (SELECT pedido_id FROM pedidos_con_parcial))
                      / (SELECT COUNT(*) FROM pedidos_entregados)
            END AS DECIMAL(6,2)
        ) AS kpi_porcentaje
    """,
]

VIEWS_DOWN = [
    "DROP VIEW IF EXISTS vw_kpi_actualizacion_cliente",
    "DROP VIEW IF EXISTS vw_kpi_resolucion_automatica",
    "DROP VIEW IF EXISTS vw_kpi_tiempo_respuesta_escalados",
    "DROP VIEW IF EXISTS vw_kpi_resolucion_imprevistos",
    "DROP VIEW IF EXISTS vw_kpi_entregas_a_tiempo",
    "DROP VIEW IF EXISTS vw_kpi_entregas_sin_observaciones",
    "DROP VIEW IF EXISTS vw_kpi_entregas_parciales",
]


def upgrade() -> None:
    for ddl in VIEWS_UP:
        op.execute(ddl)


def downgrade() -> None:
    for ddl in VIEWS_DOWN:
        op.execute(ddl)
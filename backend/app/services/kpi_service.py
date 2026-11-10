"""Consultas analíticas para el dashboard.

Todas las cifras provienen de SQL (fact_* + dim_*). La IA NO interviene.
La verificación manual está en `get_validacion()` — devuelve el SQL que
reproduce cada indicador sobre el operacional para auditoría humana.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import DimProducto

VALID_GRAINS = {"dia", "semana", "mes"}
VALID_KPIS = {
    "FREQ_ACTUALIZACION_CLIENTE",
    "TASA_RESOLUCION_AUTOMATICA",
    "TIEMPO_RESPUESTA_ESCALADOS",
    "TIEMPO_RESOLUCION_IMPREVISTOS",
    "ENTREGAS_A_TIEMPO",
    "ENTREGAS_SIN_OBSERVACIONES",
    "PCT_ENTREGAS_PARCIALES",
}


class KpiService:
    def __init__(self, db: Session):
        self.db = db

    # =================== Filtros disponibles ===================
    def get_opciones_filtros(self) -> dict[str, list[dict[str, Any]]]:
        productos = self.db.execute(
            select(DimProducto.id, DimProducto.sku, DimProducto.nombre)
            .order_by(DimProducto.nombre)
        ).all()
        return {
            "productos": [
                {"id": p[0], "sku": p[1], "nombre": p[2]} for p in productos
            ],
            "origenes": [
                {"codigo": "STOCK_TRUJILLO", "nombre": "Stock Trujillo"},
                {"codigo": "IMPORTACION", "nombre": "Importación"},
            ],
            "operadores": self._get_operadores(),
        }

    def _get_operadores(self) -> list[dict[str, Any]]:
        rows = self.db.execute(text(
            """
            SELECT DISTINCT u.id, u.nombre_completo
            FROM usuario u
            INNER JOIN usuario_rol ur ON ur.usuario_id = u.id
            INNER JOIN rol r ON r.id = ur.rol_id
            WHERE r.codigo IN ('OPERADOR', 'ADMIN') AND u.activo = 1
            ORDER BY u.nombre_completo
            """
        )).all()
        return [{"id": r[0], "nombre": r[1]} for r in rows]

    # =================== Serie temporal ===================
    def get_serie(
        self,
        codigo: str,
        *,
        desde: date,
        hasta: date,
        granularidad: str = "mes",
        producto_id: int | None = None,
        origen: str | None = None,
        operador_id: int | None = None,
    ) -> dict[str, Any]:
        if codigo not in VALID_KPIS:
            raise ValueError(f"KPI desconocido: {codigo}")
        if granularidad not in VALID_GRAINS:
            raise ValueError(f"Granularidad inválida: {granularidad}")

        if codigo == "FREQ_ACTUALIZACION_CLIENTE":
            return self._serie_freq_actualizacion(desde, hasta, granularidad,
                                                  producto_id, origen, operador_id)
        if codigo == "TASA_RESOLUCION_AUTOMATICA":
            return self._serie_resolucion(desde, hasta, granularidad,
                                          producto_id, origen, operador_id)
        if codigo == "TIEMPO_RESPUESTA_ESCALADOS":
            return self._serie_tiempo_respuesta(desde, hasta, granularidad,
                                                producto_id, origen, operador_id)
        if codigo == "TIEMPO_RESOLUCION_IMPREVISTOS":
            return self._serie_tiempo_imprevistos(desde, hasta, granularidad,
                                                  producto_id, origen, operador_id)
        if codigo == "ENTREGAS_A_TIEMPO":
            return self._serie_entregas_a_tiempo(desde, hasta, granularidad,
                                                 producto_id, origen, operador_id)
        if codigo == "ENTREGAS_SIN_OBSERVACIONES":
            return self._serie_sin_observaciones(desde, hasta, granularidad,
                                                 producto_id, origen, operador_id)
        if codigo == "PCT_ENTREGAS_PARCIALES":
            return self._serie_parciales(desde, hasta, granularidad,
                                         producto_id, origen, operador_id)
        raise ValueError(codigo)

    # --------- Filtros SQL comunes ---------
    def _where_producto(self, producto_id: int | None, *, directa: bool = False) -> str:
        """Filtro por producto.

        `directa=True` cuando la fact tiene `producto_id` (fact_hito_pedido);
        si no, subconsulta: el pedido del hecho contiene el producto.
        """
        if not producto_id:
            return ""
        if directa:
            return "AND f.producto_id = :producto_id"
        return (
            "AND f.pedido_id IN ("
            "SELECT pi.pedido_id FROM pedido_item pi "
            "WHERE pi.producto_id = :producto_id"
            ")"
        )

    def _where_origen(self, origen: str | None) -> str:
        if not origen:
            return ""
        return (
            "AND f.pedido_id IN ("
            "SELECT pi.pedido_id FROM pedido_item pi WHERE pi.origen = :origen"
            ")"
        )

    # --- Filtro por operador según la granularidad de cada fact ---
    def _where_operador_columna(self, operador_id: int | None) -> str:
        """fact_hito_pedido / fact_comunicacion: columna `operador_id` propia."""
        if operador_id is None:
            return ""
        return "AND f.operador_id = :operador_id"

    def _where_operador_caso(self, operador_id: int | None) -> str:
        """fact_escalamiento: el operador es el responsable del caso."""
        if operador_id is None:
            return ""
        return (
            "AND f.caso_id IN (SELECT c.id FROM caso_escalamiento c "
            "WHERE c.responsable_id = :operador_id)"
        )

    def _where_operador_imprevisto(self, operador_id: int | None) -> str:
        """fact_imprevisto: el operador es el responsable del imprevisto."""
        if operador_id is None:
            return ""
        return (
            "AND f.imprevisto_id IN (SELECT i.id FROM imprevisto i "
            "WHERE i.responsable_id = :operador_id)"
        )

    def _where_operador_entrega(self, operador_id: int | None) -> str:
        """fact_entrega: el operador es quien registró la entrega."""
        if operador_id is None:
            return ""
        return (
            "AND f.entrega_id IN (SELECT e.id FROM entrega e "
            "WHERE e.responsable_id = :operador_id)"
        )

    def _period_expr(self, granularidad: str) -> tuple[str, str]:
        """(select_periodo, group_by) usando dim_tiempo."""
        if granularidad == "dia":
            return ("dt.fecha", "dt.fecha")
        if granularidad == "semana":
            return (
                "CONCAT(dt.anio, '-W', "
                "RIGHT('00' + CAST(DATEPART(ISO_WEEK, dt.fecha) AS VARCHAR(2)), 2))",
                "dt.anio, DATEPART(ISO_WEEK, dt.fecha)",
            )
        return (
            "CONCAT(dt.anio, '-', RIGHT('00' + CAST(dt.mes AS VARCHAR(2)), 2))",
            "dt.anio, dt.mes",
        )

    # =========================================================
    # Implementación por KPI (los 3 filtros: producto, origen, operador)
    # =========================================================
    def _serie_freq_actualizacion(
        self, desde, hasta, gran, prod, origen, operador,
    ) -> dict:
        periodo, group = self._period_expr(gran)
        sql = f"""
            SELECT {periodo} AS periodo,
                   COUNT(*) AS total,
                   SUM(CASE WHEN f.notificado_oportuno = 1 THEN 1 ELSE 0 END) AS numerador
            FROM fact_hito_pedido f
            JOIN dim_tiempo dt ON dt.id = f.tiempo_id
            WHERE f.completado = 1
              AND dt.fecha BETWEEN :desde AND :hasta
              {self._where_producto(prod, directa=True)}
              {self._where_origen(origen)}
              {self._where_operador_columna(operador)}
            GROUP BY {group}
            ORDER BY {group}
        """
        return self._run_series(sql, desde, hasta, gran, prod, origen, operador,
                                "porcentaje")

    def _serie_resolucion(self, desde, hasta, gran, prod, origen, operador) -> dict:
        periodo, group = self._period_expr(gran)
        sql = f"""
            SELECT {periodo} AS periodo,
                   COUNT(*) AS total,
                   SUM(CASE WHEN f.escalado = 0 THEN 1 ELSE 0 END) AS numerador
            FROM fact_comunicacion f
            JOIN dim_tiempo dt ON dt.id = f.tiempo_id
            WHERE f.direccion = 'ENTRANTE' AND f.autor = 'CLIENTE'
              AND dt.fecha BETWEEN :desde AND :hasta
              {self._where_producto(prod)}
              {self._where_origen(origen)}
              {self._where_operador_columna(operador)}
            GROUP BY {group}
            ORDER BY {group}
        """
        return self._run_series(sql, desde, hasta, gran, prod, origen, operador,
                                "porcentaje")

    def _serie_tiempo_respuesta(self, desde, hasta, gran, prod, origen, operador) -> dict:
        periodo, group = self._period_expr(gran)
        sql = f"""
            SELECT {periodo} AS periodo,
                   COUNT(*) AS total,
                   AVG(CAST(f.horas_respuesta AS FLOAT)) AS numerador
            FROM fact_escalamiento f
            JOIN dim_tiempo dt ON dt.id = f.tiempo_id
            WHERE f.horas_respuesta IS NOT NULL
              AND dt.fecha BETWEEN :desde AND :hasta
              {self._where_producto(prod)}
              {self._where_origen(origen)}
              {self._where_operador_caso(operador)}
            GROUP BY {group}
            ORDER BY {group}
        """
        return self._run_series(sql, desde, hasta, gran, prod, origen, operador,
                                "promedio")

    def _serie_tiempo_imprevistos(self, desde, hasta, gran, prod, origen, operador) -> dict:
        periodo, group = self._period_expr(gran)
        sql = f"""
            SELECT {periodo} AS periodo,
                   COUNT(*) AS total,
                   AVG(CAST(f.dias_resolucion AS FLOAT)) AS numerador
            FROM fact_imprevisto f
            JOIN dim_tiempo dt ON dt.id = f.tiempo_id
            WHERE f.dias_resolucion IS NOT NULL
              AND dt.fecha BETWEEN :desde AND :hasta
              {self._where_producto(prod)}
              {self._where_origen(origen)}
              {self._where_operador_imprevisto(operador)}
            GROUP BY {group}
            ORDER BY {group}
        """
        return self._run_series(sql, desde, hasta, gran, prod, origen, operador,
                                "promedio")

    def _serie_entregas_a_tiempo(self, desde, hasta, gran, prod, origen, operador) -> dict:
        periodo, group = self._period_expr(gran)
        sql = f"""
            SELECT {periodo} AS periodo,
                   COUNT(*) AS total,
                   SUM(CASE WHEN f.a_tiempo = 1 THEN 1 ELSE 0 END) AS numerador
            FROM fact_entrega f
            JOIN dim_tiempo dt ON dt.id = f.tiempo_id
            WHERE f.tipo = 'COMPLETA'
              AND dt.fecha BETWEEN :desde AND :hasta
              {self._where_producto(prod)}
              {self._where_origen(origen)}
              {self._where_operador_entrega(operador)}
            GROUP BY {group}
            ORDER BY {group}
        """
        return self._run_series(sql, desde, hasta, gran, prod, origen, operador,
                                "porcentaje")

    def _serie_sin_observaciones(self, desde, hasta, gran, prod, origen, operador) -> dict:
        periodo, group = self._period_expr(gran)
        sql = f"""
            SELECT {periodo} AS periodo,
                   COUNT(*) AS total,
                   SUM(CASE WHEN f.con_observaciones = 0 THEN 1 ELSE 0 END) AS numerador
            FROM fact_entrega f
            JOIN dim_tiempo dt ON dt.id = f.tiempo_id
            WHERE f.tipo = 'COMPLETA'
              AND dt.fecha BETWEEN :desde AND :hasta
              {self._where_producto(prod)}
              {self._where_origen(origen)}
              {self._where_operador_entrega(operador)}
            GROUP BY {group}
            ORDER BY {group}
        """
        return self._run_series(sql, desde, hasta, gran, prod, origen, operador,
                                "porcentaje")

    def _serie_parciales(self, desde, hasta, gran, prod, origen, operador) -> dict:
        periodo, group = self._period_expr(gran)
        sql = f"""
            SELECT {periodo} AS periodo,
                   COUNT(*) AS total,
                   SUM(CASE WHEN f.tipo = 'PARCIAL' THEN 1 ELSE 0 END) AS numerador
            FROM fact_entrega f
            JOIN dim_tiempo dt ON dt.id = f.tiempo_id
            WHERE dt.fecha BETWEEN :desde AND :hasta
              {self._where_producto(prod)}
              {self._where_origen(origen)}
              {self._where_operador_entrega(operador)}
            GROUP BY {group}
            ORDER BY {group}
        """
        return self._run_series(sql, desde, hasta, gran, prod, origen, operador,
                                "porcentaje")

    # =========================================================
    # Ejecutor
    # =========================================================
    def _run_series(
        self, sql: str, desde, hasta, gran, prod, origen, operador, tipo: str,
    ) -> dict:
        params: dict[str, Any] = {"desde": desde, "hasta": hasta}
        if prod:
            params["producto_id"] = prod
        if origen:
            params["origen"] = origen
        if operador is not None:
            params["operador_id"] = operador

        rows = self.db.execute(text(sql), params).mappings().all()
        series = []
        for r in rows:
            total = int(r["total"] or 0)
            numerador = float(r["numerador"] or 0)
            if tipo == "porcentaje":
                valor = round(100.0 * numerador / total, 2) if total else None
            else:
                valor = round(numerador, 2) if total else None
            series.append({
                "periodo": str(r["periodo"]),
                "etiqueta": _format_periodo(str(r["periodo"]), gran),
                "valor": valor,
                "total": total,
                "numerador": numerador,
            })
        return {"granularidad": gran, "tipo": tipo, "serie": series}

    # =========================================================
    # Validación manual (Fase 8)
    # =========================================================
    def get_validacion(self) -> dict[str, dict[str, str]]:
        return {
            "FREQ_ACTUALIZACION_CLIENTE": {
                "definicion": "Hitos notificados ≤2h tras completarse / hitos completados ×100",
                "formula": "(notificados_oportunos / total_completados) * 100",
                "sql": (
                    "SELECT CAST(100.0 * SUM(CASE WHEN fecha_notificacion IS NOT NULL "
                    "AND DATEDIFF(HOUR, fecha_real, fecha_notificacion) <= 2 THEN 1 ELSE 0 END) "
                    "/ COUNT(*) AS DECIMAL(6,2)) AS kpi "
                    "FROM item_hito WHERE estado = 'COMPLETADO';"
                ),
            },
            "TASA_RESOLUCION_AUTOMATICA": {
                "definicion": "Consultas entrantes resueltas por el agente sin escalar",
                "formula": "(no_escaladas / total_consultas) * 100",
                "sql": (
                    "SELECT CAST(100.0 * SUM(CASE WHEN escalado = 0 THEN 1 ELSE 0 END) "
                    "/ COUNT(*) AS DECIMAL(6,2)) FROM comunicacion "
                    "WHERE direccion = 'ENTRANTE' AND autor = 'CLIENTE';"
                ),
            },
            "TIEMPO_RESPUESTA_ESCALADOS": {
                "definicion": "Horas promedio desde apertura de caso hasta primera acción humana",
                "formula": "AVG(fecha_primera_accion - fecha_apertura) en horas",
                "sql": (
                    "SELECT CAST(AVG(CAST(DATEDIFF(MINUTE, fecha_apertura, fecha_primera_accion) "
                    "AS FLOAT) / 60.0) AS DECIMAL(10,2)) FROM caso_escalamiento "
                    "WHERE fecha_primera_accion IS NOT NULL;"
                ),
            },
            "TIEMPO_RESOLUCION_IMPREVISTOS": {
                "definicion": "Días promedio desde detección hasta resolución de imprevistos",
                "formula": "AVG(fecha_resolucion - fecha_deteccion) en días",
                "sql": (
                    "SELECT CAST(AVG(CAST(DATEDIFF(MINUTE, fecha_deteccion, fecha_resolucion) "
                    "AS FLOAT) / 1440.0) AS DECIMAL(10,2)) FROM imprevisto "
                    "WHERE fecha_resolucion IS NOT NULL;"
                ),
            },
            "ENTREGAS_A_TIEMPO": {
                "definicion": "Entregas completas con fecha_real ≤ fecha_prometida",
                "formula": "(entregas_a_tiempo / entregas_completas) * 100",
                "sql": (
                    "SELECT CAST(100.0 * SUM(CASE WHEN e.fecha_real <= p.fecha_prometida "
                    "THEN 1 ELSE 0 END) / COUNT(*) AS DECIMAL(6,2)) "
                    "FROM entrega e INNER JOIN pedido p ON p.id = e.pedido_id "
                    "WHERE e.tipo = 'COMPLETA' AND e.estado = 'ENTREGADA';"
                ),
            },
            "ENTREGAS_SIN_OBSERVACIONES": {
                "definicion": "Pedidos con todos sus ítems conformes (sin observaciones)",
                "formula": "(pedidos_sin_obs / pedidos_entregados) * 100",
                "sql": (
                    "WITH entregados AS (SELECT DISTINCT e.pedido_id FROM entrega e "
                    "WHERE e.estado = 'ENTREGADA'), "
                    "con_obs AS (SELECT DISTINCT e.pedido_id FROM entrega e "
                    "INNER JOIN entrega_item ei ON ei.entrega_id = e.id "
                    "INNER JOIN conformidad c ON c.entrega_item_id = ei.id "
                    "WHERE c.resultado = 'CON_OBSERVACIONES') "
                    "SELECT CAST(100.0 * (SELECT COUNT(*) FROM entregados WHERE "
                    "pedido_id NOT IN (SELECT pedido_id FROM con_obs)) "
                    "/ (SELECT COUNT(*) FROM entregados) AS DECIMAL(6,2));"
                ),
            },
            "PCT_ENTREGAS_PARCIALES": {
                "definicion": "Pedidos con al menos una entrega parcial (indicador complementario)",
                "formula": "(pedidos_con_parcial / pedidos_entregados) * 100",
                "sql": (
                    "WITH entregados AS (SELECT DISTINCT pedido_id FROM entrega "
                    "WHERE estado = 'ENTREGADA'), "
                    "parciales AS (SELECT DISTINCT pedido_id FROM entrega "
                    "WHERE tipo = 'PARCIAL') "
                    "SELECT CAST(100.0 * (SELECT COUNT(*) FROM entregados WHERE "
                    "pedido_id IN (SELECT pedido_id FROM parciales)) "
                    "/ (SELECT COUNT(*) FROM entregados) AS DECIMAL(6,2));"
                ),
            },
        }


def _format_periodo(periodo: str, gran: str) -> str:
    """Convierte '2025-03' → 'Mar 2025', '2025-W12' → 'Sem 12 2025', '2025-03-15' → '15 Mar 2025'."""
    meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
    try:
        if gran == "mes" and "-" in periodo and "W" not in periodo:
            y, m = periodo.split("-")
            return f"{meses[int(m) - 1]} {y}"
        if gran == "semana" and "W" in periodo:
            y, w = periodo.split("-W")
            return f"Sem {int(w)} {y}"
        if gran == "dia":
            y, m, d = periodo.split("-")
            return f"{int(d)} {meses[int(m) - 1]} {y}"
    except Exception:
        pass
    return periodo
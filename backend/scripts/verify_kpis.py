"""Verificación manual de los 6 KPIs + complementario.

Ejecuta la vista de KPI (fuente del dashboard) Y el SQL equivalente sobre
el operacional (fuente de la verdad humana). Reporta diferencias.

Uso: python -m scripts.verify_kpis
"""
from __future__ import annotations

import sys
from decimal import Decimal

from sqlalchemy import text

from app.db.session import SessionLocal
from app.services.kpi_service import KpiService


CASOS_VISTA = {
    "FREQ_ACTUALIZACION_CLIENTE": "SELECT kpi_porcentaje FROM vw_kpi_actualizacion_cliente",
    "TASA_RESOLUCION_AUTOMATICA": "SELECT kpi_porcentaje FROM vw_kpi_resolucion_automatica",
    "TIEMPO_RESPUESTA_ESCALADOS": "SELECT kpi_horas_promedio FROM vw_kpi_tiempo_respuesta_escalados",
    "ENTREGAS_A_TIEMPO": "SELECT kpi_porcentaje FROM vw_kpi_entregas_a_tiempo",
    "ENTREGAS_SIN_OBSERVACIONES": "SELECT kpi_porcentaje FROM vw_kpi_entregas_sin_observaciones",
    "PCT_ENTREGAS_PARCIALES": "SELECT kpi_porcentaje FROM vw_kpi_entregas_parciales",
}


def _norm(v) -> float | None:
    if v is None:
        return None
    return float(v) if isinstance(v, Decimal) else float(v)


def main() -> int:
    db = SessionLocal()
    try:
        validacion = KpiService(db).get_validacion()
        fallos = 0
        print(f"{'KPI':40s} {'vista':>10s} {'manual':>10s} {'dif':>8s}  estado")
        for codigo, sql_vista in CASOS_VISTA.items():
            v_vista = _norm(db.execute(text(sql_vista)).scalar())
            v_manual = _norm(db.execute(text(validacion[codigo]["sql"])).scalar())
            if v_vista is None and v_manual is None:
                estado = "SIN_DATOS"
                dif = 0.0
            else:
                # tolerancia: 0.05 en % o 0.1 en horas/días
                dif = abs((v_vista or 0.0) - (v_manual or 0.0))
                estado = "OK" if dif < 0.1 else "DIFERENCIA"
                if estado == "DIFERENCIA":
                    fallos += 1
            print(
                f"{codigo:40s} "
                f"{(v_vista if v_vista is not None else -1):>10.4f} "
                f"{(v_manual if v_manual is not None else -1):>10.4f} "
                f"{dif:>8.4f}  {estado}"
            )

        # KPI 4 (imprevistos) se reporta por tipo; verificamos el total ponderado.
        v_vista_tot = _norm(db.execute(text(
            "SELECT AVG(kpi_dias_promedio) FROM vw_kpi_resolucion_imprevistos"
        )).scalar())
        v_manual_tot = _norm(db.execute(text(
            "SELECT AVG(CAST(DATEDIFF(MINUTE, fecha_deteccion, fecha_resolucion) "
            "AS FLOAT)/1440.0) FROM imprevisto WHERE fecha_resolucion IS NOT NULL"
        )).scalar())
        if v_vista_tot is None and v_manual_tot is None:
            estado = "SIN_DATOS"
            dif = 0.0
        else:
            dif = abs((v_vista_tot or 0.0) - (v_manual_tot or 0.0))
            estado = "OK" if dif < 0.1 else "DIFERENCIA"
            if estado == "DIFERENCIA":
                fallos += 1
        print(
            f"{'TIEMPO_RESOLUCION_IMPREVISTOS':40s} "
            f"{(v_vista_tot if v_vista_tot is not None else -1):>10.4f} "
            f"{(v_manual_tot if v_manual_tot is not None else -1):>10.4f} "
            f"{dif:>8.4f}  {estado}"
        )
        return 0 if fallos == 0 else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
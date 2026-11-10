"""Lectura de KPIs calculados por vistas SQL.

Todos los valores provienen de `vw_kpi_*` creadas en Fase 1.
La IA NO participa en el cálculo (principio del plan).
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models import DimKpi

from datetime import date as date_type
from sqlalchemy import select as sa_select
from app.services.kpi_service import KpiService, VALID_GRAINS, VALID_KPIS

router = APIRouter(dependencies=[Depends(get_current_user)])

# Umbrales históricos: fallback si `dim_kpi` no tiene la fila (no tumbar el
# dashboard). La fuente de verdad es `dim_kpi`, editable desde
# Admin → Catálogos sin redeploy.
_UMBRALES_FALLBACK: dict[str, tuple[float, float, float, str]] = {
    "FREQ_ACTUALIZACION_CLIENTE": (95.0, 85.0, 0.0, "mayor_mejor"),
    "TASA_RESOLUCION_AUTOMATICA": (80.0, 60.0, 0.0, "mayor_mejor"),
    "TIEMPO_RESPUESTA_ESCALADOS": (4.0, 8.0, 24.0, "menor_mejor"),
    "TIEMPO_RESOLUCION_IMPREVISTOS": (2.0, 5.0, 15.0, "menor_mejor"),
    "ENTREGAS_A_TIEMPO": (90.0, 75.0, 0.0, "mayor_mejor"),
    "ENTREGAS_SIN_OBSERVACIONES": (97.0, 90.0, 0.0, "mayor_mejor"),
    "PCT_ENTREGAS_PARCIALES": (5.0, 10.0, 25.0, "menor_mejor"),
}


def _umbrales(db: Session, codigo: str) -> tuple[float, float, float, str]:
    """(óptimo, alerta, crítico, sentido) del KPI leído de `dim_kpi`."""
    try:
        row = db.scalar(sa_select(DimKpi).where(DimKpi.codigo == codigo))
    except Exception:
        row = None
    if row is None:
        return _UMBRALES_FALLBACK[codigo]
    return (
        float(row.umbral_optimo),
        float(row.umbral_alerta),
        float(row.umbral_critico),
        row.sentido,
    )


def _semaphore(valor: float | None, sentido: str,
               optimo: float, alerta: float) -> str:
    if valor is None:
        return "SIN_DATOS"
    if sentido == "mayor_mejor":
        if valor >= optimo:
            return "OPTIMO"
        if valor >= alerta:
            return "ALERTA"
        return "CRITICO"
    # menor_mejor (horas/días)
    if valor <= optimo:
        return "OPTIMO"
    if valor <= alerta:
        return "ALERTA"
    return "CRITICO"


@router.get("/actualizacion-cliente", summary="KPI 1")
def kpi_actualizacion(db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM vw_kpi_actualizacion_cliente")).mappings().first()
    valor = float(row["kpi_porcentaje"]) if row["kpi_porcentaje"] is not None else None
    optimo, alerta, _critico, sentido = _umbrales(db, "FREQ_ACTUALIZACION_CLIENTE")
    return {
        "codigo": "FREQ_ACTUALIZACION_CLIENTE",
        "hitos_completados": row["hitos_completados"],
        "hitos_notificados_oportunos": row["hitos_notificados_oportunos"],
        "kpi_porcentaje": valor,
        "semaforo": _semaphore(valor, sentido, optimo, alerta),
        "umbrales": {"optimo": optimo, "alerta": alerta},
        "calculado_en": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/resolucion-automatica", summary="KPI 2")
def kpi_resolucion(db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM vw_kpi_resolucion_automatica")).mappings().first()
    valor = float(row["kpi_porcentaje"]) if row["kpi_porcentaje"] is not None else None
    optimo, alerta, _critico, sentido = _umbrales(db, "TASA_RESOLUCION_AUTOMATICA")
    return {
        "codigo": "TASA_RESOLUCION_AUTOMATICA",
        "total_consultas": row["total_consultas"],
        "resueltas_automaticamente": row["resueltas_automaticamente"],
        "kpi_porcentaje": valor,
        "semaforo": _semaphore(valor, sentido, optimo, alerta),
        "umbrales": {"optimo": optimo, "alerta": alerta},
        "calculado_en": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/tiempo-respuesta-escalados", summary="KPI 3")
def kpi_tiempo_respuesta(db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM vw_kpi_tiempo_respuesta_escalados")).mappings().first()
    valor = float(row["kpi_horas_promedio"]) if row["kpi_horas_promedio"] is not None else None
    optimo, alerta, _critico, sentido = _umbrales(db, "TIEMPO_RESPUESTA_ESCALADOS")
    return {
        "codigo": "TIEMPO_RESPUESTA_ESCALADOS",
        "casos_con_respuesta": row["casos_con_respuesta"],
        "kpi_horas_promedio": valor,
        "semaforo": _semaphore(valor, sentido, optimo, alerta),
        "umbrales": {"optimo": optimo, "alerta": alerta},
        "calculado_en": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/resolucion-imprevistos", summary="KPI 4")
def kpi_resolucion_imprevistos(db: Session = Depends(get_db)):
    rows = db.execute(text("SELECT * FROM vw_kpi_resolucion_imprevistos")).mappings().all()
    optimo, alerta, _critico, sentido = _umbrales(db, "TIEMPO_RESOLUCION_IMPREVISTOS")
    data = []
    total_resueltos = 0
    suma_ponderada = 0.0
    for r in rows:
        valor = float(r["kpi_dias_promedio"]) if r["kpi_dias_promedio"] is not None else None
        n = int(r["imprevistos_resueltos"] or 0)
        if valor is not None and n:
            total_resueltos += n
            suma_ponderada += valor * n
        data.append({
            "tipo": r["tipo"],
            "imprevistos_resueltos": n,
            "kpi_dias_promedio": valor,
            "semaforo": _semaphore(valor, sentido, optimo, alerta),
            "umbrales": {"optimo": optimo, "alerta": alerta},
        })
    # Media global ponderada por tipo (la tarjeta del dashboard la lee en la raíz)
    global_avg = round(suma_ponderada / total_resueltos, 2) if total_resueltos else None
    return {
        "codigo": "TIEMPO_RESOLUCION_IMPREVISTOS",
        "imprevistos_resueltos": total_resueltos,
        "kpi_dias_promedio": global_avg,
        "semaforo": _semaphore(global_avg, sentido, optimo, alerta),
        "umbrales": {"optimo": optimo, "alerta": alerta},
        "por_tipo": data,
        "calculado_en": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/entregas-a-tiempo", summary="KPI 5")
def kpi_entregas_a_tiempo(db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM vw_kpi_entregas_a_tiempo")).mappings().first()
    valor = float(row["kpi_porcentaje"]) if row["kpi_porcentaje"] is not None else None
    optimo, alerta, _critico, sentido = _umbrales(db, "ENTREGAS_A_TIEMPO")
    return {
        "codigo": "ENTREGAS_A_TIEMPO",
        "pedidos_entregados": row["pedidos_entregados"],
        "pedidos_a_tiempo": row["pedidos_a_tiempo"],
        "kpi_porcentaje": valor,
        "semaforo": _semaphore(valor, sentido, optimo, alerta),
        "umbrales": {"optimo": optimo, "alerta": alerta},
        "calculado_en": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/entregas-sin-observaciones", summary="KPI 6")
def kpi_sin_observaciones(db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM vw_kpi_entregas_sin_observaciones")).mappings().first()
    valor = float(row["kpi_porcentaje"]) if row["kpi_porcentaje"] is not None else None
    optimo, alerta, _critico, sentido = _umbrales(db, "ENTREGAS_SIN_OBSERVACIONES")
    return {
        "codigo": "ENTREGAS_SIN_OBSERVACIONES",
        "pedidos_entregados": row["pedidos_entregados"],
        "pedidos_sin_observaciones": row["pedidos_sin_observaciones"],
        "kpi_porcentaje": valor,
        "semaforo": _semaphore(valor, sentido, optimo, alerta),
        "umbrales": {"optimo": optimo, "alerta": alerta},
        "calculado_en": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/entregas-parciales", summary="Indicador complementario")
def kpi_parciales(db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM vw_kpi_entregas_parciales")).mappings().first()
    valor = float(row["kpi_porcentaje"]) if row["kpi_porcentaje"] is not None else None
    optimo, alerta, _critico, sentido = _umbrales(db, "PCT_ENTREGAS_PARCIALES")
    return {
        "codigo": "PCT_ENTREGAS_PARCIALES",
        "pedidos_entregados": row["pedidos_entregados"],
        "pedidos_con_parcial": row["pedidos_con_parcial"],
        "kpi_porcentaje": valor,
        "semaforo": _semaphore(valor, sentido, optimo, alerta),
        "umbrales": {"optimo": optimo, "alerta": alerta},
        "calculado_en": datetime.now(timezone.utc).isoformat(),
    }

@router.get("/filtros/opciones", summary="Opciones para los filtros del dashboard")
def filtros_opciones(db: Session = Depends(get_db)):
    return KpiService(db).get_opciones_filtros()


@router.get("/validacion", summary="SQL de validación manual por KPI")
def validacion():
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        return KpiService(db).get_validacion()
    finally:
        db.close()


@router.get("/{codigo}/serie", summary="Serie temporal de un KPI con filtros")
def serie(
    codigo: str,
    desde: date_type = Query(..., description="Fecha inicio (YYYY-MM-DD)"),
    hasta: date_type = Query(..., description="Fecha fin (YYYY-MM-DD)"),
    granularidad: str = Query("mes", description="dia|semana|mes"),
    producto_id: int | None = Query(None),
    origen: str | None = Query(None, description="STOCK_TRUJILLO|IMPORTACION"),
    operador_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    from fastapi import HTTPException
    if codigo not in VALID_KPIS:
        raise HTTPException(400, f"KPI desconocido: {codigo}")
    if granularidad not in VALID_GRAINS:
        raise HTTPException(400, f"Granularidad inválida: {granularidad}")
    if desde > hasta:
        raise HTTPException(400, "desde debe ser ≤ hasta")
    return KpiService(db).get_serie(
        codigo,
        desde=desde, hasta=hasta, granularidad=granularidad,
        producto_id=producto_id, origen=origen, operador_id=operador_id,
    )
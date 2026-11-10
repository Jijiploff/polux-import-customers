"""Dashboard consolidado para GERENTE / ADMIN (solo lectura)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.kpis import (
    kpi_actualizacion, kpi_entregas_a_tiempo, kpi_parciales,
    kpi_resolucion, kpi_resolucion_imprevistos, kpi_sin_observaciones,
    kpi_tiempo_respuesta,
)
from app.core.deps import require_gerente_o_admin
from app.db.session import get_db

router = APIRouter(dependencies=[Depends(require_gerente_o_admin)])


@router.get("/resumen", summary="Resumen de los 7 indicadores (snapshot actual)")
def resumen(db: Session = Depends(get_db)):
    return {
        "actualizacion_cliente": kpi_actualizacion(db),
        "resolucion_automatica": kpi_resolucion(db),
        "tiempo_respuesta_escalados": kpi_tiempo_respuesta(db),
        "resolucion_imprevistos": kpi_resolucion_imprevistos(db),
        "entregas_a_tiempo": kpi_entregas_a_tiempo(db),
        "entregas_sin_observaciones": kpi_sin_observaciones(db),
        "entregas_parciales": kpi_parciales(db),
    }
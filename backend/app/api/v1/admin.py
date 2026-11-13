"""Operaciones administrativas: ejecución manual del motor de reglas y ETL."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models import (
    Alerta,
    CasoEscalamiento,
    EstadoAlerta,
    EstadoCaso,
    EstadoHito,
    ItemHito,
    MotivoEscalamiento,
    Pedido,
    TipoAlerta,
)
from app.services.fact_sync_service import FactSyncService
from app.services.rule_engine import RuleEngine

from app.services.telegram_service import TelegramService

router = APIRouter(dependencies=[Depends(require_admin)])


def _rules_snapshot(db: Session) -> dict[str, int]:
    """Obtiene el estado relevante antes y después de una corrida."""
    return {
        "pedidos_total": db.scalar(select(func.count(Pedido.id))) or 0,
        "hitos_atrasados": db.scalar(
            select(func.count(ItemHito.id)).where(
                ItemHito.estado == EstadoHito.ATRASADO
            )
        ) or 0,
        "alertas_abiertas": db.scalar(
            select(func.count(Alerta.id)).where(
                Alerta.estado == EstadoAlerta.ABIERTA
            )
        ) or 0,
        "alertas_retraso_critico": db.scalar(
            select(func.count(Alerta.id)).where(
                Alerta.tipo == TipoAlerta.RETRASO_CRITICO,
                Alerta.estado == EstadoAlerta.ABIERTA,
            )
        ) or 0,
        "casos_retraso_critico": db.scalar(
            select(func.count(CasoEscalamiento.id)).where(
                CasoEscalamiento.motivo == MotivoEscalamiento.RETRASO_CRITICO,
                CasoEscalamiento.estado.in_(
                    [EstadoCaso.ABIERTO, EstadoCaso.EN_PROCESO]
                ),
            )
        ) or 0,
    }


@router.post("/run-rules", summary="Ejecuta el motor de reglas (manual)")
def run_rules(db: Session = Depends(get_db)):
    before = _rules_snapshot(db)
    counts = RuleEngine(db).run_all()
    return {
        "before": before,
        "counts": counts,
        "after": _rules_snapshot(db),
    }


@router.post("/sync-facts", summary="Sincroniza el modelo dimensional (manual)")
def sync_facts(db: Session = Depends(get_db)):
    return {"counts": FactSyncService(db).sync_all()}

@router.post("/telegram/set-webhook", summary="Configura el webhook de Telegram")
def telegram_set_webhook(payload: dict):
    url = payload.get("url")
    if not url:
        from fastapi import HTTPException
        raise HTTPException(400, "Falta 'url'")
    tg = TelegramService()
    return tg.set_webhook(url, secret_token=tg.webhook_secret or None)


@router.post("/telegram/delete-webhook", summary="Elimina el webhook de Telegram")
def telegram_delete_webhook():
    return TelegramService().delete_webhook()


@router.get("/telegram/webhook-info", summary="Info del webhook de Telegram")
def telegram_webhook_info():
    return TelegramService().get_webhook_info()
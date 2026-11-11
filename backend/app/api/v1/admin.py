"""Operaciones administrativas: ejecución manual del motor de reglas y ETL."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.services.fact_sync_service import FactSyncService
from app.services.rule_engine import RuleEngine

from app.services.telegram_service import TelegramService

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/run-rules", summary="Ejecuta el motor de reglas (manual)")
def run_rules(db: Session = Depends(get_db)):
    counts = RuleEngine(db).run_all()
    return {"counts": counts}


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
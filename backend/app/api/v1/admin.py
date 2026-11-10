"""Operaciones administrativas: ejecución manual del motor de reglas y ETL."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.services.fact_sync_service import FactSyncService
from app.services.rule_engine import RuleEngine

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/run-rules", summary="Ejecuta el motor de reglas (manual)")
def run_rules(db: Session = Depends(get_db)):
    counts = RuleEngine(db).run_all()
    return {"counts": counts}


@router.post("/sync-facts", summary="Sincroniza el modelo dimensional (manual)")
def sync_facts(db: Session = Depends(get_db)):
    return {"counts": FactSyncService(db).sync_all()}
"""Endpoint operativo para forzar el despacho del outbox (solo ADMIN)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.services.outbox_worker import OutboxWorker

router = APIRouter(dependencies=[Depends(require_admin)])


@router.post("/run", summary="Ejecuta el outbox worker manualmente")
def run_outbox(db: Session = Depends(get_db)):
    return {"counts": OutboxWorker(db).process_batch()}
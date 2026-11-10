"""Scheduler: motor de reglas + outbox + sync de hechos."""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("scheduler")
_scheduler: BackgroundScheduler | None = None


def run_rule_engine_once() -> None:
    from app.db.session import SessionLocal
    from app.services.rule_engine import RuleEngine
    db = SessionLocal()
    try:
        logger.info("rule_engine_run_ok counts=%s", RuleEngine(db).run_all())
    except Exception:
        logger.exception("rule_engine_run_failed")
    finally:
        db.close()


def run_outbox_once() -> None:
    from app.db.session import SessionLocal
    from app.services.outbox_worker import OutboxWorker
    db = SessionLocal()
    try:
        logger.info("outbox_run_ok counts=%s", OutboxWorker(db).process_batch())
    except Exception:
        logger.exception("outbox_run_failed")
    finally:
        db.close()


def run_fact_sync_once() -> None:
    from app.db.session import SessionLocal
    from app.services.fact_sync_service import FactSyncService
    db = SessionLocal()
    try:
        logger.info("fact_sync_ok counts=%s", FactSyncService(db).sync_all())
    except Exception:
        logger.exception("fact_sync_failed")
    finally:
        db.close()


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    s = get_settings()
    if not s.SCHEDULER_ENABLED:
        logger.info("scheduler_disabled")
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(run_rule_engine_once,
                       IntervalTrigger(seconds=s.SCHEDULER_INTERVAL_SECONDS),
                       id="rule_engine", max_instances=1, coalesce=True,
                       replace_existing=True)
    if s.OUTBOX_ENABLED:
        _scheduler.add_job(run_outbox_once,
                           IntervalTrigger(seconds=s.OUTBOX_INTERVAL_SECONDS),
                           id="outbox", max_instances=1, coalesce=True,
                           replace_existing=True)
    # Sync de hechos cada 5 minutos (independiente del resto)
    _scheduler.add_job(run_fact_sync_once, IntervalTrigger(seconds=300),
                       id="fact_sync", max_instances=1, coalesce=True,
                       replace_existing=True)
    _scheduler.start()
    logger.info(
        "scheduler_started rules=%ss outbox=%ss facts=300s",
        s.SCHEDULER_INTERVAL_SECONDS, s.OUTBOX_INTERVAL_SECONDS,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("scheduler_stopped")
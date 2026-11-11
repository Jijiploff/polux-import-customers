"""Polling de Telegram para desarrollo local (sin ngrok).

Uso:
    docker compose exec backend python -m scripts.telegram_poll
"""
from __future__ import annotations

import signal
import sys
import time

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.services.telegram_handler import handle_telegram_update
from app.services.telegram_service import TelegramService

configure_logging()
logger = get_logger("telegram_poll")


def main() -> int:
    s = get_settings()
    if not s.TELEGRAM_ENABLED or not s.TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_ENABLED y TELEGRAM_BOT_TOKEN son obligatorios")
        return 1

    tg = TelegramService()
    try:
        tg.delete_webhook()
        logger.info("webhook_removed_for_polling")
    except Exception as exc:
        logger.warning("delete_webhook_failed err=%s", tg.redact(str(exc)))

    last_update_id: int | None = None
    stop = {"flag": False}

    def _shutdown(signum, frame):
        logger.info("shutdown_signal sig=%s", signum)
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("telegram_polling_started")
    while not stop["flag"]:
        try:
            updates = tg.get_updates(offset=last_update_id, timeout=30)
        except Exception as exc:
            logger.exception("get_updates_error err=%s", tg.redact(str(exc)))
            time.sleep(2)
            continue

        for upd in updates:
            db = SessionLocal()
            try:
                result = handle_telegram_update(db, upd, telegram=tg)
                logger.info("update_processed result=%s", result)
            except Exception:
                logger.exception("update_process_error")
            finally:
                db.close()
            uid = upd.get("update_id")
            if isinstance(uid, int):
                last_update_id = uid + 1

    logger.info("telegram_polling_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
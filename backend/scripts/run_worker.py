"""Worker dedicado: corre scheduler (reglas + outbox + sync de hechos) sin
exponer FastAPI.

En producción, el backend corre con múltiples workers gunicorn (SCHEDULER_ENABLED=false)
y este proceso se ejecuta como un único servicio `worker` en docker-compose.prod.yml.
Así se evita que el scheduler corra N veces en paralelo.
"""
from __future__ import annotations

import signal
import sys
import time

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.services.scheduler import start_scheduler, stop_scheduler

configure_logging()
logger = get_logger("worker")


def main() -> int:
    settings = get_settings()
    if not settings.SCHEDULER_ENABLED:
        logger.warning(
            "worker_started_but_scheduler_disabled env=%s — forzando true", settings.APP_ENV
        )
        settings.SCHEDULER_ENABLED = True
    start_scheduler()
    logger.info("worker_ready")

    stop_flag = {"stop": False}

    def _handler(signum, frame):
        logger.info("worker_signal sig=%s", signum)
        stop_flag["stop"] = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)
    while not stop_flag["stop"]:
        time.sleep(1)
    stop_scheduler()
    logger.info("worker_stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
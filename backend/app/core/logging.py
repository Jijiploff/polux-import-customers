"""Logging estructurado en JSON para observabilidad."""
import logging

from pythonjsonlogger import jsonlogger

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(
        jsonlogger.JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(settings.LOG_LEVEL.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
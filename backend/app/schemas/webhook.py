"""Esquemas para los webhooks de WhatsApp."""
from typing import Any

from pydantic import BaseModel


class WebhookVerificationResponse(BaseModel):
    challenge: str


class WebhookAckResponse(BaseModel):
    status: str = "ok"
    processed: int = 0
    duplicated: int = 0
    statuses_updated: int = 0
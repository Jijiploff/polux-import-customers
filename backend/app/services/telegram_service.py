"""Cliente HTTP para la Bot API de Telegram (sin dependencias extra)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("telegram_service")


@dataclass
class TelegramSendResult:
    ok: bool
    message_id: int | None
    error: str | None = None
    retriable: bool = False


class TelegramService:
    def __init__(self):
        s = get_settings()
        self.enabled = s.TELEGRAM_ENABLED
        self.token = s.TELEGRAM_BOT_TOKEN
        self.webhook_secret = s.TELEGRAM_WEBHOOK_SECRET
        self.operator_chat_id = s.TELEGRAM_OPERATOR_CHAT_ID
        self.timeout = s.TELEGRAM_API_TIMEOUT_SECONDS
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""

    def _ready(self) -> bool:
        return bool(self.enabled and self.token and self.base_url)

    # ---------- Envío ----------
    def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        parse_mode: str | None = None,
        disable_notification: bool = False,
    ) -> TelegramSendResult:
        if not self._ready():
            return TelegramSendResult(ok=False, message_id=None, error="telegram_disabled")
        if not text:
            return TelegramSendResult(ok=False, message_id=None, error="empty_text")

        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text[:4000],
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(f"{self.base_url}/sendMessage", json=payload)
        except httpx.HTTPError as exc:
            logger.exception("telegram_send_http_error err=%s", exc)
            return TelegramSendResult(ok=False, message_id=None, error=str(exc), retriable=True)

        if r.status_code == 200:
            data = r.json()
            return TelegramSendResult(
                ok=True, message_id=(data.get("result") or {}).get("message_id")
            )

        retriable = r.status_code == 429 or r.status_code >= 500
        try:
            desc = r.json().get("description", f"HTTP {r.status_code}")
        except Exception:
            desc = f"HTTP {r.status_code}: {r.text[:200]}"
        logger.warning("telegram_send_failed status=%s desc=%s", r.status_code, desc)
        return TelegramSendResult(ok=False, message_id=None, error=desc, retriable=retriable)

    # ---------- Webhook ----------
    def set_webhook(self, url: str, secret_token: str | None = None) -> dict[str, Any]:
        if not self._ready():
            return {"ok": False, "description": "telegram_disabled"}
        payload: dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/setWebhook", json=payload)
        r.raise_for_status()
        return r.json()

    def delete_webhook(self) -> dict[str, Any]:
        if not self._ready():
            return {"ok": False, "description": "telegram_disabled"}
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/deleteWebhook")
        r.raise_for_status()
        return r.json()

    def get_webhook_info(self) -> dict[str, Any]:
        if not self._ready():
            return {"ok": False, "description": "telegram_disabled"}
        with httpx.Client(timeout=self.timeout) as client:
            r = client.get(f"{self.base_url}/getWebhookInfo")
        r.raise_for_status()
        return r.json()

    # ---------- Polling ----------
    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        if not self._ready():
            return []
        params: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        with httpx.Client(timeout=timeout + 10) as client:
            r = client.get(f"{self.base_url}/getUpdates", params=params)
        if r.status_code != 200:
            logger.warning("telegram_get_updates_failed status=%s", r.status_code)
            return []
        return r.json().get("result", [])
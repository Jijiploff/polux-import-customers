"""Cliente del WhatsApp Business Cloud API (Meta Graph).

Diseño:
- `WhatsAppService` encapsula el envío de **plantillas aprobadas** y de
  **texto libre** (dentro de la ventana de 24h) contra Graph API.
- `WhatsAppResult` normaliza la respuesta de Meta.
- En `WHATSAPP_DRY_RUN=true` no se llama a Meta: devuelve un `wamid`
  sintético `dryrun.<uuid>` y lo marca `dry_run=True`. Esto permite probar
  TODO el flujo localmente sin credenciales reales.

Errores de Meta manejados:
- 131047 → fuera de ventana 24h: no reintentar free-form, usar plantilla.
- 131026 → número inválido/no WhatsApp: terminal, no reintentar.
- 132000 → parámetros de plantilla no coinciden: terminal, error de código.
- 190    → token inválido: terminal (requiere intervención).
- 130429 → rate limit: backoff largo (lo gestiona el worker).
- 5xx / timeout → reintentar con backoff.
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("whatsapp_service")


@dataclass
class WhatsAppResult:
    ok: bool
    wamid: str | None
    status: str  # "sent" | "failed" | "dry_run"
    error_code: int | None = None
    error_message: str | None = None
    retriable: bool = False
    dry_run: bool = False


class WhatsAppService:
    # Códigos de Meta que NO deben reintentarse
    _TERMINAL_CODES = {131026, 131047, 132000, 190, 100, 131051}
    # Códigos que indican rate limit → backoff largo
    _RATE_LIMIT_CODES = {130429, 131056}

    def __init__(self):
        s = get_settings()
        self.enabled = s.WHATSAPP_ENABLED
        self.dry_run = s.WHATSAPP_DRY_RUN or not self.enabled
        self.token = s.WHATSAPP_TOKEN
        self.phone_id = s.WHATSAPP_PHONE_NUMBER_ID
        self.verify_token = s.WHATSAPP_VERIFY_TOKEN
        self.app_secret = s.WHATSAPP_APP_SECRET
        self.graph_version = s.WHATSAPP_GRAPH_VERSION
        self.timeout = s.WHATSAPP_API_TIMEOUT_SECONDS
        self.base_url = f"https://graph.facebook.com/{self.graph_version}"

    # =====================================================================
    # Envío de plantillas
    # =====================================================================
    def send_template(
        self,
        *,
        to: str,
        template_name: str,
        language_code: str = "es_PE",
        body_params: list[str] | None = None,
    ) -> WhatsAppResult:
        """Envía una plantilla aprobada. `to` debe incluir código de país (sin +)."""
        if self.dry_run:
            logger.info(
                "whatsapp_dry_run_template to=%s template=%s params=%s",
                to, template_name, body_params,
            )
            return WhatsAppResult(
                ok=True, wamid=f"dryrun.{uuid.uuid4().hex}",
                status="dry_run", dry_run=True,
            )

        payload = {
            "messaging_product": "whatsapp",
            "to": self._normalize_phone(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": (
                    [{
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": str(p)} for p in (body_params or [])
                        ],
                    }] if body_params else []
                ),
            },
        }
        return self._post_messages(payload)

    # =====================================================================
    # Envío de texto libre (dentro de ventana de 24h)
    # =====================================================================
    def send_text(self, *, to: str, body: str) -> WhatsAppResult:
        if self.dry_run:
            logger.info("whatsapp_dry_run_text to=%s len=%s", to, len(body))
            return WhatsAppResult(
                ok=True, wamid=f"dryrun.{uuid.uuid4().hex}",
                status="dry_run", dry_run=True,
            )
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._normalize_phone(to),
            "type": "text",
            "text": {"preview_url": False, "body": body},
        }
        return self._post_messages(payload)

    # =====================================================================
    # Verificación de webhook
    # =====================================================================
    def verify_webhook_challenge(
        self, mode: str, token: str, challenge: str
    ) -> str | None:
        if mode == "subscribe" and hmac.compare_digest(token, self.verify_token):
            return challenge
        return None

    # =====================================================================
    # Verificación de firma HMAC-SHA256
    # =====================================================================
    def verify_signature(self, raw_body: bytes, signature_header: str) -> bool:
        # Fail-closed: sin cabecera de firma o sin App Secret no se puede
        # validar la autenticidad del remitente → se rechaza siempre.
        if not signature_header or not signature_header.startswith("sha256="):
            logger.warning("whatsapp_signature_missing")
            return False
        if not self.app_secret:
            logger.error("whatsapp_app_secret_missing")
            return False
        expected = "sha256=" + hmac.new(
            self.app_secret.encode("utf-8"), raw_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header)

    # =====================================================================
    # Helpers
    # =====================================================================
    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Meta espera solo dígitos, con código de país, sin + ni espacios."""
        return "".join(c for c in phone if c.isdigit())

    def _post_messages(self, payload: dict) -> WhatsAppResult:
        url = f"{self.base_url}/{self.phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            logger.warning("whatsapp_timeout err=%s", exc)
            return WhatsAppResult(
                ok=False, wamid=None, status="failed",
                error_message="timeout", retriable=True,
            )
        except httpx.HTTPError as exc:
            logger.exception("whatsapp_http_error err=%s", exc)
            return WhatsAppResult(
                ok=False, wamid=None, status="failed",
                error_message=str(exc), retriable=True,
            )

        if r.status_code == 200:
            data = r.json()
            wamid = (data.get("messages") or [{}])[0].get("id")
            logger.info("whatsapp_sent wamid=%s", wamid)
            return WhatsAppResult(ok=True, wamid=wamid, status="sent")

        # Error de Meta
        try:
            err = r.json().get("error", {})
        except Exception:
            err = {}
        code = err.get("code")
        msg = err.get("message", f"HTTP {r.status_code}")
        logger.warning("whatsapp_error status=%s code=%s msg=%s", r.status_code, code, msg)

        retriable = False
        if code in self._RATE_LIMIT_CODES:
            retriable = True
        elif code in self._TERMINAL_CODES:
            retriable = False
        elif r.status_code >= 500:
            retriable = True

        return WhatsAppResult(
            ok=False, wamid=None, status="failed",
            error_code=code, error_message=msg, retriable=retriable,
        )
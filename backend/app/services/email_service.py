"""Canal de respaldo por correo electrónico.

Proveedores soportados:
- `mock`   → registra en log, no envía (para pruebas locales).
- `resend` → API HTTP de Resend (`https://api.resend.com/emails`).
- `smtp`   → envío SMTP con aiosmtplib.

Se usa cuando:
- `comunicacion.canal = EMAIL` (el cliente no tiene WhatsApp).
- Fallback definitivo tras N reintentos de WhatsApp (último recurso).
"""
from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("email_service")


@dataclass
class EmailResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
    dry_run: bool = False


class EmailService:
    def __init__(self):
        s = get_settings()
        self.enabled = s.EMAIL_ENABLED
        self.provider = s.EMAIL_PROVIDER.lower()
        self.api_key = s.EMAIL_API_KEY
        self.from_addr = s.EMAIL_FROM
        self.from_name = s.EMAIL_FROM_NAME
        self.smtp_host = s.SMTP_HOST
        self.smtp_port = s.SMTP_PORT
        self.smtp_user = s.SMTP_USER
        self.smtp_password = s.SMTP_PASSWORD
        self.smtp_tls = s.SMTP_USE_TLS

    def send(self, *, to: str, subject: str, body: str) -> EmailResult:
        if not self.enabled or self.provider == "mock":
            logger.info("email_mock to=%s subject=%s", to, subject)
            return EmailResult(ok=True, provider_message_id="mock", dry_run=True)
        if self.provider == "resend":
            return self._send_resend(to=to, subject=subject, body=body)
        if self.provider == "smtp":
            return self._send_smtp_sync(to=to, subject=subject, body=body)
        return EmailResult(ok=False, error=f"provider desconocido: {self.provider}")

    # ---------- Resend ----------
    def _send_resend(self, *, to: str, subject: str, body: str) -> EmailResult:
        if not self.api_key:
            return EmailResult(ok=False, error="EMAIL_API_KEY vacío")
        payload = {
            "from": f"{self.from_name} <{self.from_addr}>",
            "to": [to],
            "subject": subject,
            "text": body,
        }
        try:
            with httpx.Client(timeout=15) as client:
                r = client.post(
                    "https://api.resend.com/emails",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            if r.status_code in (200, 201):
                return EmailResult(ok=True, provider_message_id=r.json().get("id"))
            return EmailResult(ok=False, error=f"resend {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as exc:
            return EmailResult(ok=False, error=str(exc))

    # ---------- SMTP (sync vía smtplib para no exigir aiosmtplib) ----------
    def _send_smtp_sync(self, *, to: str, subject: str, body: str) -> EmailResult:
        import smtplib
        msg = EmailMessage()
        msg["From"] = f"{self.from_name} <{self.from_addr}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15) as smtp:
                if self.smtp_tls:
                    smtp.starttls()
                if self.smtp_user:
                    smtp.login(self.smtp_user, self.smtp_password)
                smtp.send_message(msg)
            return EmailResult(ok=True, provider_message_id=None)
        except (smtplib.SMTPException, OSError) as exc:
            logger.exception("smtp_error")
            return EmailResult(ok=False, error=str(exc))
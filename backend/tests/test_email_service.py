"""Email service: mock no envía, provider desconocido falla."""
from app.core.config import get_settings
from app.services.email_service import EmailService


def test_email_mock(monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "mock")
    get_settings.cache_clear()
    r = EmailService().send(to="x@y.com", subject="s", body="b")
    assert r.ok is True
    assert r.dry_run is True


def test_email_disabled(monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    get_settings.cache_clear()
    r = EmailService().send(to="x@y.com", subject="s", body="b")
    assert r.ok is True  # provider mock


def test_email_provider_desconocido(monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("EMAIL_PROVIDER", "foo")
    get_settings.cache_clear()
    r = EmailService().send(to="x@y.com", subject="s", body="b")
    assert r.ok is False
    assert "desconocido" in (r.error or "")
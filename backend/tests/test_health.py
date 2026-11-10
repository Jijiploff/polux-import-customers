"""Pruebas mínimas de Fase 0: la app responde y el health reporta OK."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_root_ok():
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"]
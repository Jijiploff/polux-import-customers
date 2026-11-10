"""Pruebas de seguridad: JWT, RBAC, firma webhook, SQL injection."""
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.core.config import get_settings
from app.core.security import create_access_token


def test_token_manipulado_rechazado(client):
    tok = create_access_token("x@y.com", ["OPERADOR"])
    # Firmar con otra clave (manipulación)
    payload = jwt.get_unverified_claims(tok)
    payload["roles"] = ["ADMIN"]
    fake = jwt.encode(payload, "otra-clave", algorithm="HS256")
    r = client.get("/api/v1/usuarios", headers={"Authorization": f"Bearer {fake}"})
    assert r.status_code == 401


def test_token_expirado(client):
    s = get_settings()
    payload = {
        "sub": "t.oper@example.com",
        "roles": ["OPERADOR"],
        "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
    }
    tok = jwt.encode(payload, s.JWT_SECRET_KEY, algorithm=s.JWT_ALGORITHM)
    r = client.get("/api/v1/pedidos", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_operador_no_accede_a_usuarios(client, auth):
    r = client.get("/api/v1/usuarios", headers=auth["operador"])
    assert r.status_code == 403


def test_operador_no_accede_a_reglas(client, auth):
    r = client.patch("/api/v1/reglas/1", headers=auth["operador"], json={"valor": "999"})
    assert r.status_code == 403


def test_gerente_solo_lectura(client, auth):
    r = client.patch("/api/v1/reglas/1", headers=auth["gerente"], json={"valor": "999"})
    assert r.status_code == 403


def test_webhook_sin_firma_rechazado(client):
    r = client.post("/api/v1/webhooks/whatsapp",
                    json={"entry": []})
    assert r.status_code == 401


def test_webhook_firma_incorrecta_rechazado(client):
    body = json.dumps({"entry": []}).encode()
    r = client.post(
        "/api/v1/webhooks/whatsapp", content=body,
        headers={"X-Hub-Signature-256": "sha256=deadbeef",
                 "Content-Type": "application/json"},
    )
    assert r.status_code == 401


def test_endpoint_sin_token_devuelve_401(client):
    for path in [
        "/api/v1/pedidos",
        "/api/v1/kpis/actualizacion-cliente",
        "/api/v1/casos",
        "/api/v1/comunicaciones",
    ]:
        r = client.get(path)
        assert r.status_code == 401, f"{path} debe requerir auth"


def test_sql_injection_en_filtro_numerico(client, auth):
    # Intento clásico; el ORM parametriza y devuelve 422 por tipo.
    r = client.get(
        "/api/v1/pedidos?cliente_id=1%20OR%201=1",
        headers=auth["operador"],
    )
    # FastAPI valida como int → 422 (no expone la BD)
    assert r.status_code in (400, 422)


def test_sql_injection_en_string_enum(client, auth):
    r = client.get(
        "/api/v1/pedidos?estado=ABIERTO%27%20OR%20%271%27%3D%271",
        headers=auth["operador"],
    )
    # Enum rechaza el valor → 422
    assert r.status_code == 422
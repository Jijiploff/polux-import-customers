"""Fixtures compartidos. Desactiva el scheduler en los tests."""
import os
from typing import Iterator

# Debe ejecutarse antes de importar la app
os.environ["SCHEDULER_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import Rol, RolCodigo, Usuario, UsuarioRol

get_settings.cache_clear()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


def _get_or_create_user(db, email: str, roles: list[RolCodigo]) -> Usuario:
    user = db.scalar(select(Usuario).where(Usuario.email == email))
    if user is None:
        user = Usuario(email=email, nombre_completo=email,
                       password_hash=hash_password("Test123!"), activo=True)
        db.add(user)
        db.flush()
        for codigo in roles:
            rol = db.scalar(select(Rol).where(Rol.codigo == codigo))
            if rol:
                db.add(UsuarioRol(usuario_id=user.id, rol_id=rol.id))
        db.commit()
    return user


@pytest.fixture(scope="session")
def tokens():
    db = SessionLocal()
    try:
        admin = _get_or_create_user(db, "t.admin@example.com", [RolCodigo.ADMIN])
        oper = _get_or_create_user(db, "t.oper@example.com", [RolCodigo.OPERADOR])
        ger = _get_or_create_user(db, "t.ger@example.com", [RolCodigo.GERENTE])
        return {
            "admin": create_access_token(admin.email, ["ADMIN"]),
            "operador": create_access_token(oper.email, ["OPERADOR"]),
            "gerente": create_access_token(ger.email, ["GERENTE"]),
        }
    finally:
        db.close()


def _header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth(tokens):
    return {
        "admin": _header(tokens["admin"]),
        "operador": _header(tokens["operador"]),
        "gerente": _header(tokens["gerente"]),
    }
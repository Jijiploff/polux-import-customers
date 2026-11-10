"""Dependencias de FastAPI: usuario autenticado y guardas por rol."""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models import RolCodigo, Usuario

_settings = get_settings()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{_settings.API_V1_PREFIX}/auth/login")

_401 = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Credenciales inválidas",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db),
) -> Usuario:
    try:
        payload = decode_token(token)
    except ValueError:
        raise _401
    user = db.scalar(select(Usuario).where(Usuario.email == payload.get("sub")))
    if user is None or not user.activo:
        raise _401
    return user


def _user_role_codes(user: Usuario) -> set[RolCodigo]:
    return {r.rol.codigo for r in user.roles if r.rol is not None}


def require_roles(*roles: RolCodigo):
    """Factory de dependencia que exige al usuario pertenecer a alguno de los roles."""
    allowed = set(roles)

    def _checker(user: Usuario = Depends(get_current_user)) -> Usuario:
        if not (_user_role_codes(user) & allowed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permiso denegado")
        return user

    return _checker


require_admin = require_roles(RolCodigo.ADMIN)
require_operador = require_roles(RolCodigo.ADMIN, RolCodigo.OPERADOR)
require_gerente_o_admin = require_roles(RolCodigo.ADMIN, RolCodigo.GERENTE)
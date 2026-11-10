"""Autenticación: login + perfil del usuario autenticado."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import Usuario
from app.schemas.auth import LoginRequest, TokenResponse, UserMe

router = APIRouter()


@router.post("/login", response_model=TokenResponse, summary="Login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(Usuario).where(Usuario.email == payload.email))
    if user is None or not user.activo or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")
    roles = [r.rol.codigo.value for r in user.roles if r.rol]
    user.ultimo_login = datetime.utcnow()
    db.commit()
    token = create_access_token(subject=user.email, roles=roles)
    return TokenResponse(access_token=token, roles=roles, nombre=user.nombre_completo)


@router.get("/me", response_model=UserMe, summary="Perfil del usuario autenticado")
def me(user: Usuario = Depends(get_current_user)) -> UserMe:
    return UserMe(
        id=user.id,
        email=user.email,
        nombre=user.nombre_completo,
        roles=[r.rol.codigo.value for r in user.roles if r.rol],
    )
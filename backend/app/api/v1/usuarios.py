"""CRUD de usuarios (solo ADMIN)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Rol, RolCodigo, Usuario, UsuarioRol
from app.schemas.admin import UsuarioCreate, UsuarioRead, UsuarioUpdate

router = APIRouter()


def _serialize(u: Usuario) -> UsuarioRead:
    return UsuarioRead(
        id=u.id,
        email=u.email,
        nombre_completo=u.nombre_completo,
        activo=u.activo,
        ultimo_login=u.ultimo_login,
        roles=[r.rol.codigo for r in u.roles if r.rol],
    )


def _sync_roles(db: Session, user: Usuario, roles_codigos: list[RolCodigo]) -> None:
    db.query(UsuarioRol).filter(UsuarioRol.usuario_id == user.id).delete()
    db.flush()
    for codigo in roles_codigos:
        rol = db.scalar(select(Rol).where(Rol.codigo == codigo))
        if rol is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Rol {codigo} inexistente")
        db.add(UsuarioRol(usuario_id=user.id, rol_id=rol.id))


@router.get("", response_model=list[UsuarioRead], dependencies=[Depends(require_admin)])
def listar(db: Session = Depends(get_db)):
    return [_serialize(u) for u in db.scalars(select(Usuario).order_by(Usuario.id)).all()]


@router.post("", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin)])
def crear(payload: UsuarioCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Usuario).where(Usuario.email == payload.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email ya registrado")
    user = Usuario(
        email=payload.email,
        nombre_completo=payload.nombre_completo,
        password_hash=hash_password(payload.password),
        activo=True,
    )
    db.add(user)
    db.flush()
    _sync_roles(db, user, payload.roles)
    db.commit()
    db.refresh(user)
    return _serialize(user)


@router.patch("/{usuario_id}", response_model=UsuarioRead, dependencies=[Depends(require_admin)])
def actualizar(usuario_id: int, payload: UsuarioUpdate, db: Session = Depends(get_db)):
    user = db.get(Usuario, usuario_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    if payload.nombre_completo is not None:
        user.nombre_completo = payload.nombre_completo
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
    if payload.activo is not None:
        user.activo = payload.activo
    if payload.roles is not None:
        _sync_roles(db, user, payload.roles)
    db.commit()
    db.refresh(user)
    return _serialize(user)
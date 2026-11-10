"""Hashing de contraseñas y emisión/verificación de JWT."""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

_settings = get_settings()


def hash_password(password: str) -> str:
    """Hashea la contraseña con bcrypt (salt único por hash)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica la contraseña contra un hash bcrypt."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(subject: str, roles: list[str]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "roles": roles,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=_settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)).timestamp()
        ),
    }
    return jwt.encode(
        payload, _settings.JWT_SECRET_KEY, algorithm=_settings.JWT_ALGORITHM
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(
            token, _settings.JWT_SECRET_KEY, algorithms=[_settings.JWT_ALGORITHM]
        )
    except JWTError as exc:
        raise ValueError(f"Token inválido: {exc}") from exc
"""Endpoints de salud (aplicación y base de datos)."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter()
settings = get_settings()


@router.get("/health", summary="Health de la aplicación")
def health():
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.APP_ENV,
    }


@router.get("/health/db", summary="Health de la base de datos")
def health_db(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        # Devolvemos 503 para que Docker/K8s marquen el contenedor como unhealthy.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Base de datos no accesible: {exc}",
        )
    return {"status": "ok", "database": settings.DB_NAME, "host": settings.DB_HOST}
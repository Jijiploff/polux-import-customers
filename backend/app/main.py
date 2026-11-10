"""Punto de entrada FastAPI — versión de producción."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.rate_limit import RateLimitMiddleware
from app.services.scheduler import (
    run_rule_engine_once, start_scheduler, stop_scheduler,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    log = get_logger("app.startup")
    log.info("startup", extra={"env": settings.APP_ENV, "version": settings.APP_VERSION})
    if settings.SCHEDULER_ENABLED and settings.SCHEDULER_RUN_ON_STARTUP:
        run_rule_engine_once()
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()
        log.info("shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.APP_ENV != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

# Orden importante: CORS debe ser el middleware MÁS EXTERNO para que sus
# cabeceras (incluido el 429 del rate limit) lleguen al navegador y para
# que el preflight OPTIONS no consuma cuota de login.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "version": settings.APP_VERSION}
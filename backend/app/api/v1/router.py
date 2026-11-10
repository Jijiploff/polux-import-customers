"""Enrutador raíz de la API v1."""
from fastapi import APIRouter

from app.api.v1 import (
    admin, agent, alertas, auth, casos, catalogos, comunicaciones,
    dashboard, entregas, health, hitos, imprevistos, items, kpis,
    outbox, pedidos, reglas, usuarios, webhooks,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(usuarios.router, prefix="/usuarios", tags=["Usuarios"])
api_router.include_router(pedidos.router, prefix="/pedidos", tags=["Pedidos"])
api_router.include_router(items.router, prefix="/items", tags=["Items"])
api_router.include_router(hitos.router, prefix="/hitos", tags=["Hitos"])
api_router.include_router(entregas.router, prefix="/entregas", tags=["Entregas"])
api_router.include_router(casos.router, prefix="/casos", tags=["Casos"])
api_router.include_router(imprevistos.router, prefix="/imprevistos", tags=["Imprevistos"])
api_router.include_router(comunicaciones.router, prefix="/comunicaciones", tags=["Comunicaciones"])
api_router.include_router(alertas.router, prefix="/alertas", tags=["Alertas"])
api_router.include_router(reglas.router, prefix="/reglas", tags=["Reglas"])
api_router.include_router(catalogos.router, prefix="/catalogos", tags=["Catálogos"])
api_router.include_router(kpis.router, prefix="/kpis", tags=["KPIs"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(admin.router, prefix="/admin", tags=["Admin"])
api_router.include_router(agent.router, prefix="/agent", tags=["Agente IA"])
api_router.include_router(outbox.router, prefix="/outbox", tags=["Outbox"])
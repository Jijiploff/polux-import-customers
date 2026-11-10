"""Rate limiting por IP + ruta.

Almacenamiento en memoria con ventana deslizante simple. Suficiente para
piloto en 1 instancia. Para producción multi-instancia se recomienda Redis;
ver README-DEPLOY.md. Se aplica solo a rutas sensibles (auth, webhooks,
agent) para no penalizar las lecturas normales del dashboard.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# (max_peticiones, ventana_segundos) por prefijo de ruta
_LIMITES: list[tuple[str, int, int]] = [
    ("/api/v1/auth/login", 10, 60),          # 10 logins/min/IP
    ("/api/v1/webhooks/whatsapp", 600, 60),  # Meta puede enviar lotes
    ("/api/v1/agent/messages/incoming", 60, 60),
    ("/api/v1/", 600, 60),                   # resto de la API
]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        limite: tuple[int, int] | None = None
        for prefix, max_req, ventana in _LIMITES:
            if path.startswith(prefix):
                limite = (max_req, ventana)
                break
        if limite is None:
            return await call_next(request)

        max_req, ventana = limite
        ip = request.client.host if request.client else "unknown"
        key = (ip, path.split("/")[3] if len(path.split("/")) > 3 else path)
        ahora = time.monotonic()
        bucket = self._buckets[key]

        # Limpia ventana
        while bucket and bucket[0] < ahora - ventana:
            bucket.popleft()

        if len(bucket) >= max_req:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit excedido ({max_req} por {ventana}s)",
            )
        bucket.append(ahora)
        return await call_next(request)
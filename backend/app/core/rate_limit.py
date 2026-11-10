"""Rate limiting por IP + ruta.

Almacenamiento en memoria con ventana deslizante simple. Suficiente para
piloto en 1 instancia. Para producción multi-instancia se recomienda Redis;
ver README-DEPLOY.md. Se aplica solo a rutas sensibles (auth, webhooks,
agent) para no penalizar las lecturas normales del dashboard.
"""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

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
        # Clave por ruta completa (IDs → :id). Antes se usaba el segmento[3],
        # lo que agrupaba /auth/login con /auth/me: cada recarga de página
        # consumía la cuota de login y en 10 cargas el login devolvía 429.
        key_path = re.sub(r"/\d+", "/:id", path)
        key = (ip, key_path)
        ahora = time.monotonic()
        bucket = self._buckets[key]

        # Limpia ventana
        while bucket and bucket[0] < ahora - ventana:
            bucket.popleft()

        if len(bucket) >= max_req:
            # Se devuelve la respuesta (NO se lanza la excepción): esta
            # ejecución ocurre POR ENCIMA del ExceptionMiddleware, y una
            # excepción sin manejar llegaría al navegador como 500 sin
            # cabeceras CORS → el frontend mostraría un error de CORS
            # en vez del mensaje de rate limit.
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": f"Rate limit excedido ({max_req} por {ventana}s)"},
            )
        bucket.append(ahora)
        return await call_next(request)
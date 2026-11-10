# Estado de sesión — compacto (para reanudar rápido)

> Compendio operativo. El roadmap vivo está en `PLAN_FASES.md`.

## Entorno (verificado)
- Repo: `C:\Users\LENOVO\Documents\PROGRAMAS\polux-import-customers` (git, branch `main`, usuario git: Zaleth Valentina Rivas Calderón)
- Docker: ruta no estándar `%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe` (iniciar si el daemon no responde)
- Stack: `docker compose up -d --build` → 3 contenedores: `polux_db` (SQL Server 2022, healthy, puerto 1433), `polux_backend` (8000, uvicorn --reload), `polux_frontend` (5173)
- BD: `PoluxImportDB`, usuario `sa`, pass `Polux#Strong!Pwd2025` (sqlcmd en contenedor: `/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P ...`)
- Login admin: `admin@poluximport.pe` / `Admin123!` (también operador/`Oper123!`, gerente/`Ger123!`)
- Alembic head: `0005_comunicacion_wamid_filtered`
- Modo: **LLM = Gemini ACTIVO** (`LLM_PROVIDER=openai`, `gemini-3.1-flash-lite` + respaldo `gemini-3.5-flash`, motor local mock como último recurso; RateGuard: `LLM_RPM=5`, reposo 60 s tras 429; **tests = mock** por conftest para no gastar cuota). WhatsApp dry_run, Email mock (`.env` creado desde `.env.example`)
- Comandos clave: `docker compose exec -T backend python -m scripts.<x>`, `docker compose exec -T backend pytest -q`, `docker compose exec -T backend alembic upgrade head`
- Quirks PowerShell: sin operador `??`; `Select-String` puede devolver exit 1 sin ser error; warning compose por atributo `version` (cosmético)

## Fases (ver PLAN_FASES.md para detalle)
- **0 Plan ✅ / A Datos demo ✅** — commit `53bbdf4`
- **Docs I ✅** — `01`, `03`, `04` (commit `df17b1a`)
- **B ✅** — umbrales de `dim_kpi` + filtros en las 7 series (commit `de7f10c`)
- **Docs II ✅** — `02-flujos.md` (8 diagramas), `05-manual-usuario.md` (18 capturas), `06-api.md`, README; fixes rate-limit/CORS/KPI global (commit `50dd648`)
- **C ✅** — página `/agente` (simulador + métricas + test de clasificación, menú ADMIN/OPERADOR) + botones **+ Nuevo caso / + Nuevo imprevisto / + Nuevo mensaje**; verificación e2e 10/10 (`frontend/scripts/verificar-fase-c.mjs`, temporal, no versionado); build `npm run build` y `npm test` en verde (fixes: types vitest/globals, specs e2e fuera de vitest, token en test Alertas, replaceAll, null-check NuevaEntrega); manual 05 ampliado (§12 agente + capturas 17/18)
- **T ✅** — de 17 fallas + 2 errores a **90 tests en verde** y repetibles (2 corridas seguidas, conteos de BD idénticos, cero residuo). Fixes: `tests/db_utils.py` nuevo (`cleanup_pedido` con orden FK seguro + circularidad `comunicacion.caso_id ↔ caso` + borrado de cliente huérfano; `crear_pedido_listo`); cleanups centralizados en 8 archivos de test; fixture `db` añadido a `test_e2e_flow`; `date`→`datetime` en `test_kpis_serie`; 5 tests dejaron de operar sobre el "primer pedido" (demo cerrado → 409) y usan pedido propio; `verify_signature` fail-closed (sin bypass dry_run); `MockProvider` marca daño como NEGATIVO; `GET /` responde; `.env.example` con verify token coherente (`polux-verify-token`) y sin claves duplicadas muertas. Residuo histórico de la BD (13 pedidos, 70 clientes huérfanos, casos/imprevistos de test sobre la demo) purgado
- **G1 ✅** — Gemini activo: `LLM_PROVIDER=openai` + `LLM_BASE_URL` de Gemini, modelo `gemini-3.1-flash-lite` con `LLM_MODEL_FALLBACK=gemini-3.5-flash` (503 en el principal → respaldo automático, verificado en vivo: clasificó `ESTADO_PEDIDO` en 8.9 s). Frugalidad: `RateGuard` (ventana deslizante `LLM_RPM=5`/60 s, reposo 60 s tras 429 sin reintentar, `LLM_MAX_RETRIES=1` solo para 5xx, presupuesto total `LLM_TIMEOUT_SECONDS=20`, reintento sin `response_format` si el modelo no lo soporta). Cualquier fallo → motor local (mock), `LLMNoDisponible` tipado; `POST /agent/test/classify` ya no devuelve 500 si el LLM cae (usa mock y lo avisa). Tests aislados (`conftest.py` fuerza `LLM_PROVIDER=mock`) + `tests/test_llm_provider.py` (8 tests: cuota, RateGuard, confianza) → **98 tests en verde**. Docs: `01`, `04` (§5 y §11), `06`, `PLAN_FASES`, `.env.example` (sin la key)
- **Siguiente**: Fase G2 — simulador de chat WhatsApp (página + endpoints de hilo y respuesta humana)
- **C2 futuro**: Telegram (definido en 04-agente.md); n8n descartado (justificado en doc); LLM = Gemini vía endpoint OpenAI-compatible (solo `.env`)

## Bugs encontrados y CORREGOS (commiteados con Fase A)
1. `comunicacion.whatsapp_message_id` UNIQUE nullable → SQL Server 23000 con el 2º NULL → motor de reglas caído desde el arranque → migración 0005 (índice único filtrado `WHERE IS NOT NULL`)
2. Modelo `Comunicacion` sin relación `plantilla` → outbox `AttributeError` → añadida en `comms.py`
3. `FactComunicacion` sin `operador_id` (columna existe desde mig. 0004) → fact_sync TypeError → añadido en `analytics.py`

## Fase A — datos demo (script `backend/scripts/demo_dashboard_data.py`)
- Idempotente (sale si ya hay `entrega`); cubre: hitos completados con notif controlada (9/10 oportunas), 4 comms entrantes (3 consultas + 1 reclamo), caso RECLAMO resuelto (1ª acción 3.5h), 2 imprevistos (resuelto 3d + abierto), corre RuleEngine + Outbox + fact_sync, entrega COMPLETA (p1, conforme) + PARCIAL autorizada ADMIN (p2, con observación)
- Resultado `/api/v1/dashboard/resumen`: actualizacion_cliente 90% ALERTA · resolucion_automatica 75% ALERTA · tiempo_respuesta 3.5h OPTIMO · entregas_a_tiempo 100% OPTIMO · sin_observaciones 50% CRITICO · parciales 50% CRITICO · imprevistos por_tipo=1
- Estado BD: 3 pedidos (p1 CERRADO, p2 con parcial+imprevisto, p3 en curso), 10 comms, alertas 2, casos 3, imprevistos 2, fact_* poblados (fh=10, fc=13)
- Scheduler OK: `rule_engine_run_ok`, outbox enviando, `fact_sync_ok`

## Decisiones de diseño (respuesta del usuario)
- Manual: audiencia **usuario del cliente** (paso a paso + capturas, sin jerga)
- Telegram: **definir en doc, implementar después**
- n8n: **descartado**, documentar por qué (ya existe orquestación interna + trazabilidad en BD)
- Diagramas: **Mermaid** en `docs/`; E-R generado desde modelos SQLAlchemy
- Commits por fase estable

## Criterio de fase estable
Dashboard con valores ✅ (Fase A) → commitear → Docs I → B → Docs II → C → **T ✅ (2026-11-10): plan completo**

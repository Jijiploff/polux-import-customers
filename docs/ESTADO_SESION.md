# Estado de sesión — compacto (para reanudar rápido)

> Compendio operativo. El roadmap vivo está en `PLAN_FASES.md`.

## Entorno (verificado)
- Repo: `C:\Users\LENOVO\Documents\PROGRAMAS\polux-import-customers` (git, branch `main`, usuario git: Zaleth Valentina Rivas Calderón)
- Docker: ruta no estándar `%LOCALAPPDATA%\Programs\DockerDesktop\Docker Desktop.exe` (iniciar si el daemon no responde)
- Stack: `docker compose up -d --build` → 3 contenedores: `polux_db` (SQL Server 2022, healthy, puerto 1433), `polux_backend` (8000, uvicorn --reload), `polux_frontend` (5173)
- BD: `PoluxImportDB`, usuario `sa`, pass `Polux#Strong!Pwd2025` (sqlcmd en contenedor: `/opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P ...`)
- Login admin: `admin@poluximport.pe` / `Admin123!` (también operador/`Oper123!`, gerente/`Ger123!`)
- Alembic head: `0005_comunicacion_wamid_filtered`
- Modo simulado: LLM=mock, WhatsApp dry_run, Email mock (`.env` creado desde `.env.example`)
- Comandos clave: `docker compose exec -T backend python -m scripts.<x>`, `docker compose exec -T backend pytest -q`, `docker compose exec -T backend alembic upgrade head`
- Quirks PowerShell: sin operador `??`; `Select-String` puede devolver exit 1 sin ser error; warning compose por atributo `version` (cosmético)

## Fases (ver PLAN_FASES.md para detalle)
- **0 Plan ✅ / A Datos demo ✅** — commitear (pendiente al cortar)
- **Docs I ⬜**: `01-arquitectura.md`, `03-modelo-er.md`, `04-agente.md` (Mermaid, en español)
- **B ⬜**: umbrales KPI leídos de `dim_kpi` (hoy hardcodeados en `kpis.py::_semaphore`) + filtros de series ignorados en `kpi_service.py` (líneas ~107, 181, 188-249)
- **Docs II ✅**: `02-flujos.md` (8 diagramas), `05-manual-usuario.md` (12 tareas por rol con 16 capturas regeneradas con datos limpios), `06-api.md` (generado desde OpenAPI), README reescrito; fixes: rate-limit 429 con CORS + key por ruta completa, KPI 4 con valor global ponderado
- **Siguiente**: Fase C (página del agente IA + botones crear caso/imprevisto/comunicación) → Fase T (~13 tests preexistentes)
- **C ⬜**: UI agente IA + botones crear caso/imprevisto/comunicación (endpoints ya existen)
- **T ⬜**: reparar ~13 tests rotos (aislamiento BD compartida, teardowns FK, `datetime.date` sin tz en test_kpis_serie, `GET /` 404, firma webhook no rechaza) — baseline verificado: fallaban ANTES de los fixes
- **C2 futuro**: Telegram (definir en 04-agente.md); n8n descartado (justificar en doc); LLM = Gemini vía endpoint OpenAI-compatible (solo `.env`)

## Bugs encontrados y CORREGOS (commiteados con Fase A)
1. `comunicacion.whatsapp_message_id` UNIQUE nullable → SQL Server 23000 con el 2º NULL → motor de reglas caído desde el arranque → migración 0005 (índice único filtrado `WHERE IS NOT NULL`)
2. Modelo `Comunicacion` sin relación `plantilla` → outbox `AttributeError` → añadida en `comms.py`
3. `FactComunicacion` sin `operador_id` (columna existe desde mig. 0004) → fact_sync TypeError → añadido en `analytics.py`

## Fase A — datos demo (script `backend/scripts/demo_dashboard_data.py`)
- Idempotente (sale si ya hay `entrega`); cubre: hitos completados con notif controlada (9/10 oportunas), 4 comms entrantes (3 consultas + 1 reclamo), caso RECLAMO resuelto (1ª acción 3.5h), 2 imprevistos (resuelto 3d + abierto), corre RuleEngine + Outbox + fact_sync, entrega COMPLETA (p1, conforme) + PARCIAL autorizada ADMIN (p2, con observación)
- Resultado `/api/v1/dashboard/resumen`: actualizacion_cliente 90% ALERTA · resolucion_automatica 75% ALERTA · tiempo_respuesta 3.5h OPTIMO · entregas_a_tiempo 100% OPTIMO · sin_observaciones 50% CRITICO · parciales 50% CRITICO · imprevistos por_tipo=1
- Estado BD: 3 pedidos (p1 CERRADO, p2 con parcial+imprevisto, p3 en curso), ~14 comms (SENT+entrantes), alertas 2, casos 3, fact_* poblados
- Scheduler OK: `rule_engine_run_ok`, outbox enviando, `fact_sync_ok`

## Decisiones de diseño (respuesta del usuario)
- Manual: audiencia **usuario del cliente** (paso a paso + capturas, sin jerga)
- Telegram: **definir en doc, implementar después**
- n8n: **descartado**, documentar por qué (ya existe orquestación interna + trazabilidad en BD)
- Diagramas: **Mermaid** en `docs/`; E-R generado desde modelos SQLAlchemy
- Commits por fase estable

## Criterio de fase estable
Dashboard con valores ✅ (Fase A) → commitear → Docs I → B → Docs II → C → T

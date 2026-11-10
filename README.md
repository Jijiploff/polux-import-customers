# Polux Import · Fase Customers

Sistema de **seguimiento y atención al cliente** para importaciones:
agente IA de acompañamiento (actualizaciones proactivas, alertas de
retraso, escalamiento de casos), gestión web de pedidos/entregas y
dashboard de KPIs.

> 📖 Documentación completa en [`docs/`](docs/) ·
> Guía de levantamiento detallada en [`LEVANTAMIENTO.md`](LEVANTAMIENTO.md) ·
> Roadmap y estado en [`docs/PLAN_FASES.md`](docs/PLAN_FASES.md)

## Requisitos

- Docker Desktop 4.x (o Docker Engine + Compose v2)
- 4 GB de RAM disponibles para los contenedores

## Puesta en marcha

```bash
cp .env.example .env
make up                     # levanta db + backend + frontend
make init-db                # crea PoluxImportDB si no existe
make migrate                # aplica migraciones Alembic (0001 → 0005)
make seed                   # catálogos, plantillas, usuarios, dim_kpi
make test-data              # pedidos de prueba (3 pedidos, 25 hitos)
```

Poblar el dashboard con la historia demo (hitos, entregas, casos,
imprevistos, comunicaciones) y verificar los 7 KPIs:

```bash
docker compose exec -T backend python -m scripts.demo_dashboard_data
```

> En Windows sin `make`: los mismos comandos están documentados paso a
> paso en [`LEVANTAMIENTO.md`](LEVANTAMIENTO.md).

## Credenciales y URLs (entorno local)

| Acceso | Valor |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/api/v1/docs |
| SQL Server | `localhost,1433` — usuario `sa`, contraseña de `.env` |
| Admin | `admin@poluximport.pe` / `Admin123!` |
| Operador | `operador@poluximport.pe` / `Oper123!` |
| Gerente | `gerente@poluximport.pe` / `Ger123!` |

## Modo simulado vs productivo

Por defecto el sistema corre **sin integraciones reales** (solo `.env`,
el código no cambia):

| Integración | Default local | Productivo |
|---|---|---|
| LLM (agente) | `LLM_PROVIDER=mock` (clasificación por keywords) | `openai` + `LLM_BASE_URL` compatible (Gemini) + `LLM_API_KEY` |
| WhatsApp | `WHATSAPP_DRY_RUN=true` (envíos ficticios) | `WHATSAPP_ENABLED=true` + token de Meta |
| Email | `EMAIL_PROVIDER=mock` | `resend` o `smtp` |

## Estructura

```
├── docker-compose.yml     # 3 servicios: db, backend, frontend
├── Makefile               # up / migrate / seed / test / …
├── docs/                  # documentación con diagramas Mermaid
│   ├── PLAN_FASES.md      # roadmap y estado por fase
│   ├── 01-arquitectura.md # stack, capas, orquestación
│   ├── 02-flujos.md       # 8 flujos del negocio
│   ├── 03-modelo-er.md    # 31 tablas (E-R)
│   ├── 04-agente.md       # definición del agente + Telegram + no-n8n
│   ├── 05-manual-usuario.md  # manual por rol (usuarios del cliente)
│   └── 06-api.md          # referencia de la API
├── backend/
│   ├── alembic/versions/  # migraciones 0001…0005
│   ├── app/
│   │   ├── api/v1/        # 19 routers (JWT + roles)
│   │   ├── models/        # SQLAlchemy (operacional + dimensional)
│   │   ├── schemas/       # Pydantic
│   │   └── services/      # reglas, agente, outbox, ETL, KPIs
│   ├── scripts/           # seed_data / test_data / demo_dashboard_data
│   └── tests/             # suite pytest
└── frontend/              # React + Vite + TypeScript (15 páginas)
```

## Tests

```bash
make test                  # pytest dentro del contenedor backend
```

> ⚠️ Known issue: la suite tiene ~13 tests con fallos pre-existentes de
> aislamiento (corren contra la BD real; ver Fase T en
> [`docs/PLAN_FASES.md`](docs/PLAN_FASES.md)).

## Operación útil

```bash
make logs                  # logs de los 3 servicios
docker compose exec -T backend alembic upgrade head   # migrar
docker compose exec -T backend alembic current        # versión actual
```

Endpoints de operación manual (ADMIN, vía Swagger o curl):
`POST /api/v1/admin/run-rules` (motor de reglas),
`POST /api/v1/admin/sync-facts` (ETL dimensional),
`POST /api/v1/outbox/run` (despachar cola de mensajes).

## Stack

**SQL Server 2022 · FastAPI (Python 3.11) · SQLAlchemy + Alembic ·
React 18 + Vite + TypeScript · APScheduler · LLM compatible OpenAI
(Gemini) · WhatsApp Business Cloud API · Docker Compose**

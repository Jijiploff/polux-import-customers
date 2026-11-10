
### 4.24 `PROGRESO_DESARROLLO.md` (versión FINAL)

```markdown
# PROGRESO DE DESARROLLO — Polux Import · Fase Customers

## Estado general
✅ **TODAS LAS FASES (0-8) COMPLETADAS.**

## Fases terminadas

### Fase 0 — Preparación y estructura ✅
Docker compose (dev) con db/backend/frontend, env, logging JSON,
health checks, Alembic, esqueleto React/TS.

### Fase 1 — Base de datos ✅
31 tablas (13 operativas + RBAC + adaptadores + 12 dimensionales),
7 vistas KPI, migraciones 0001-0002, seeds, 3 pedidos de prueba.

### Fase 2 — Backend y API ✅
~45 endpoints REST, RBAC (ADMIN/OPERADOR/GERENTE), Pydantic v2,
auditoría (created_by_id/updated_by_id), validaciones backend.

### Fase 3 — Motor de reglas ✅
RuleEngine con 9 reglas idempotentes, scheduler (APScheduler),
plantillas, idempotencia, verificación de consentimiento (Ley 29733).

### Fase 4 — Agente IA ✅
LLMProvider abstracto (Mock + OpenAI-compatible), 7 guardrails
(no decide, no inventa fechas, no ofrece parcial, no resuelve
reclamos, fallback determinista), endpoint `/agent/messages/incoming`.

### Fase 5 — Integraciones ✅
WhatsApp Cloud API (webhooks firmados HMAC-SHA256, outbox worker,
backoff exponencial), correo de respaldo (Resend/SMTP).
Modo dry_run que permite probar TODO el flujo sin credenciales reales.

### Fase 6 — Frontend de gestión ✅
React 18 + TypeScript + Vite, login, guards por rol, 15 páginas:
pedidos (con hitos), comunicaciones, casos, imprevistos, entregas
(con formulario de autorización de parcial), conformidad, admin
(usuarios/reglas/catálogos).

### Fase 7 — Dashboard y KPIs ✅
7 indicadores (6 + complementario), semáforos parametrizables,
filtros (periodo, producto, origen, operador), gráficos con
recharts, ETL `FactSyncService` (idempotente), `/kpis/{codigo}/serie`,
`/kpis/validacion` (SQL reproducible).

### Fase 8 — Pruebas y despliegue ✅
Suite completa backend (unit, integración, E2E, seguridad), Playwright
frontend, rate limit, Dockerfiles productivos (gunicorn + nginx),
`docker-compose.prod.yml` con worker dedicado, backups/restore,
`scripts/verify_kpis.py`, `README-DEPLOY.md`.

## Archivos clave por fase

Ver `README-DEPLOY.md` §2 y las entregas previas (documentadas en este
mismo archivo a medida que se entregaron).

## Estructura actual del proyecto
polux-import-customers/
├── backend/ FastAPI + SQLAlchemy + Alembic + scheduler
├── frontend/ React + TS + Vite + Playwright
├── scripts/ backup.sh, restore.sh
├── docker-compose.yml (dev)
├── docker-compose.prod.yml (prod)
├── .env.example
├── .env.prod.example
└── README-DEPLOY.md


## Decisiones técnicas

| Decisión | Justificación |
|---|---|
| Sync SQLAlchemy 2.0 | SQL Server + pyodbc es estable; FastAPI corre endpoints sync en threadpool |
| JWT HS256 | Simplicidad para 1 tenant; cambiar a RS256 si se añaden servicios externos |
| Logging JSON desde Fase 0 | Auditoría y observabilidad |
| Scheduler en proceso dedicado (`worker`) | Evita doble ejecución con N workers gunicorn |
| Modo `dry_run` en WhatsApp | Permite probar TODO el flujo sin credenciales reales |
| Fallback MockProvider en agent | Resiliencia ante caída del LLM real |
| Facts con clave natural idempotente | `_sync_*` nunca duplica por corridas repetidas |
| Rate limit en memoria | Suficiente para piloto; migrar a Redis para multi-instancia |

## Dependencias

- Python 3.11, FastAPI 0.115, SQLAlchemy 2.0.35, pyodbc 5.1, alembic 1.13,
  pydantic 2.9, passlib[bcrypt], python-jose, APScheduler, gunicorn.
- Node 20, React 18.3, Vite 5.4, TypeScript 5.5, react-router-dom 6.26,
  recharts 2.12, @playwright/test 1.47.
- SQL Server 2022.

## Configuraciones

- `.env` (dev), `.env.prod` (prod). Ver `.env.example` / `.env.prod.example`.
- `docker-compose.yml` (dev) / `docker-compose.prod.yml` (prod).

## Problemas conocidos / Limitaciones

- Rate limit en memoria (no distribuido).
- WhatsApp 24h window requiere `whatsapp_template_id` en plantillas críticas
  para envíos fuera de ventana.
- CORS debe configurarse al dominio real en producción.
- El scheduler vive en el servicio `worker`; monitorear que esté corriendo.

## Verificación de aceptación (contra §12 del plan)

| Criterio | Verificado en |
|---|---|
| Pedido verificado recibe bienvenida | Fase 3 + E2E test |
| Seguimiento por ítem | Fase 2/6 + E2E test |
| Estado del pedido = ítem más atrasado | `pedido_service._estado_por_items` |
| Hitos notifican en plazo | Fase 3 + vista KPI 1 |
| Notificaciones consolidadas | `_rule_aviso_hito` (agrupación por pedido) |
| Alertas y escalamientos | Fases 3 + tests `test_rule_engine.py` |
| Reclamos escalados sin resolver | Fase 4 guardrail + test |
| No entrega completa con ítems pendientes | `entrega_service.crear_entrega` + test |
| No entrega parcial sin autorización humana | CHECK BD + servicio + UI + test |
| Cada comunicación registrada | `comunicacion` (todas las fases) |
| Trazabilidad de escalamientos | `caso_escalamiento` (Fase 3-4) |
| Imprevisto con seguimiento y cierre | `imprevisto` + `_rule_imprevisto` |
| No cierra pedido sin conformidad | `_cerrar_o_actualizar_pedido` |
| 6 KPIs por SQL + verificación manual | `scripts/verify_kpis.py` retorna 0 |
| Roles respetan permisos | `test_security.py` |
| Agente no inventa ni decide | 7 guardrails + `test_agent.py` |
| Sistema integrado (no módulos aislados) | `test_e2e_flow.py` |

## Próximos pasos (post-piloto, NO parte de este alcance)

- Migrar rate limit a Redis si se escala a N>1 backend.
- Integrar tracking de courier automático (reemplaza la actualización manual de hitos).
- Panel BI externo (Power BI) sobre `vw_kpi_*` si se prefiere.
- App móvil para operadores de entrega.
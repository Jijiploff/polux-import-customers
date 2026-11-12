# 🚀 Levantamiento del sistema — Polux Import · Fase Customers

Guía completa para clonar, configurar y ejecutar el sistema de seguimiento
y atención al cliente de Polux Import en un entorno local.

---

## 📋 Tabla de contenido

1. [Descripción del proyecto](#1-descripción-del-proyecto)
2. [Stack tecnológico](#2-stack-tecnológico)
3. [Requisitos previos](#3-requisitos-previos)
4. [Instalación — Windows](#4-instalación--windows)
5. [Instalación — Mac / Linux](#5-instalación--mac--linux)
6. [Credenciales de acceso](#6-credenciales-de-acceso)
7. [URLs del sistema](#7-urls-del-sistema)
8. [Comandos útiles](#8-comandos-útiles)
9. [Arquitectura y módulos](#9-arquitectura-y-módulos)
10. [Fixes aplicados durante el setup](#10-fixes-aplicados-durante-el-setup)
11. [Troubleshooting](#11-troubleshooting)
12. [Estado del proyecto](#12-estado-del-proyecto)
13. [Próximos pasos](#13-próximos-pasos)

---

## 1. Descripción del proyecto

**Polux Import · Fase Customers** es el sistema de seguimiento y atención
al cliente del importador peruano de productos Apple. Cubre el ciclo completo
desde que un pedido ingresa con el primer pago verificado hasta la entrega
con conformidad por ítem.

### Módulos implementados

- **Gestión de pedidos** con seguimiento por ítem e hitos (stock/importación).
- **Motor de reglas** con scheduler (bienvenida, avisos de hito, retrasos,
  imprevistos, escalamientos, silencio del cliente).
- **Agente IA** acotado (clasifica intención, redacta mensajes desde BD, escala
  reclamos/daños/entregas parciales sin decidir).
- **Integración WhatsApp** Business Cloud API (modo `dry_run` sin credenciales
  reales) + correo de respaldo.
- **Sistema web** con roles ADMIN / OPERADOR / GERENTE.
- **Dashboard** con 7 KPIs calculados por SQL (nunca por IA).

---

## 2. Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic |
| Base de datos | Microsoft SQL Server 2022 (en Docker) |
| Frontend | React 18 + TypeScript + Vite + Recharts |
| Agente IA | Provider configurable (Mock local + OpenAI-compatible) |
| Mensajería | WhatsApp Business Cloud API + correo (Resend/SMTP) |
| Scheduler | APScheduler (reglas, outbox, sync de hechos) |
| Contenedores | Docker + Docker Compose v2 |
| Pruebas | Pytest + Vitest + Playwright |

---

## 3. Requisitos previos

| Componente | Versión mínima |
|---|---|
| Docker Desktop / Docker Engine | 24+ |
| Docker Compose | v2 (plugin) |
| RAM libre | 4 GB (SQL Server consume ~2 GB) |
| Disco libre | ~8 GB |
| Puertos libres | `1433`, `8000`, `5173` |

Verifica con:

```bash
docker --version
docker compose version
```

> ⚠️ **En Windows**: Docker Desktop debe estar corriendo con WSL2 habilitado.
> Si tienes un SQL Server local en el puerto 1433, ver sección
> [Troubleshooting](#11-troubleshooting) para resolver el conflicto de puerto.

---

## 4. Instalación — Windows

Todos los comandos se ejecutan en **CMD** desde la carpeta raíz del proyecto.

### 4.1 Clonar el repositorio

```cmd
cd C:\ruta\donde\quieras
git clone <URL_DEL_REPO> polux-import-customers
cd polux-import-customers
```

### 4.2 Configurar variables de entorno

```cmd
copy .env.example .env
notepad .env
```

Verifica que contenga **al menos** estos valores (los del `.env.example`
por defecto ya funcionan para desarrollo local):

```env
MSSQL_SA_PASSWORD=Polux#Strong!Pwd2025
DB_PASSWORD=Polux#Strong!Pwd2025
DB_HOST=db
DB_NAME=PoluxImportDB
DB_USER=sa
SCHEDULER_ENABLED=true
WHATSAPP_DRY_RUN=true
LLM_PROVIDER=mock
EMAIL_PROVIDER=mock
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<token-de-BotFather>
TELEGRAM_WEBHOOK_SECRET=<secreto-aleatorio>
TELEGRAM_OPERATOR_CHAT_ID=
```

> ⚠️ **Importante**: `MSSQL_SA_PASSWORD` debe cumplir la política de SQL Server
> (≥ 8 caracteres, mayúscula, minúscula, dígito, símbolo). Si no la cumple, el
> contenedor `db` no arranca.

### 4.3 Levantar el stack

```cmd
docker compose up -d --build
```

Esto puede tardar **5–10 minutos la primera vez** (descarga SQL Server 2022,
compila backend y frontend).

Verifica que los 4 contenedores estén corriendo:

```cmd
docker compose ps
```

Esperado:
```
polux_db          Up (healthy)
polux_backend     Up
polux_telegram_poll Up
polux_frontend    Up
```

> Si `db` dice solo `Up` sin `(healthy)`, espera 30-60 s más y vuelve a ejecutar
> `docker compose ps`.

### 4.4 Inicializar la base de datos

```cmd
:: Crear la BD
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2025" -Q "IF DB_ID('PoluxImportDB') IS NULL CREATE DATABASE PoluxImportDB"

:: Aplicar todas las migraciones (incluye la tabla coordinacion_entrega)
docker compose exec -T backend alembic upgrade head

:: Cargar seeds (roles, usuarios demo, hitos, SLA, plantillas, reglas, KPIs)
docker compose exec -T backend python -m scripts.seed_data

:: Cargar pedidos de prueba (3 pedidos con ítems mixtos)
docker compose exec -T backend python -m scripts.test_data
```

Salidas esperadas:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial_schema
INFO  [alembic.runtime.migration] Running upgrade 0001_initial_schema -> 0002_kpi_views
INFO  [alembic.runtime.migration] Running upgrade 0002_kpi_views -> 0003_outbox_columns
INFO  [alembic.runtime.migration] Running upgrade 0003_outbox_columns -> 0004_fact_columns
INFO  [alembic.runtime.migration] Running upgrade 0011_idempotency_keys -> 0012_delivery_workflow

[seed] OK
[seed] fact_sync: {...}

[test_data] OK — 3 pedidos, 5 ítems, hitos generados.
```

### 4.5 Verificar que todo funciona

```cmd
curl http://localhost:8000/api/v1/health
```
→ `{"status":"ok",...}`

```cmd
curl http://localhost:8000/api/v1/health/db
```
→ `{"status":"ok","database":"PoluxImportDB","host":"db"}`

Abre en el navegador: **http://localhost:5173**

### 4.6 Verificar Telegram

El servicio `telegram_poll` usa `getUpdates` en desarrollo local. Al iniciar,
elimina cualquier webhook anterior para evitar que webhook y polling compitan.

```cmd
:: Debe mostrar TELEGRAM_ENABLED=true y token_configured=True
docker compose exec -T telegram_poll python -c "from app.core.config import get_settings; s=get_settings(); print(s.TELEGRAM_ENABLED, bool(s.TELEGRAM_BOT_TOKEN))"

:: Debe devolver ok=true, url vacía y pending_update_count
docker compose exec -T telegram_poll python -c "from app.services.telegram_service import TelegramService; print(TelegramService().get_webhook_info())"

:: Debe mostrar webhook_removed_for_polling y telegram_polling_started
docker compose logs --tail=50 telegram_poll
```

Si la API está activa pero el bot no responde, revisa primero:

```cmd
docker compose logs --tail=100 telegram_poll
docker compose exec -T backend alembic current
```

La revisión debe ser `0012_delivery_workflow (head)`. Si no lo es, ejecuta:

```cmd
docker compose exec -T backend alembic upgrade head
docker compose restart telegram_poll
```

---

## 5. Instalación — Mac / Linux

Idéntico al flujo de Windows, con comandos shell:

```bash
# 1. Clonar
git clone <URL_DEL_REPO> polux-import-customers
cd polux-import-customers

# 2. Configurar entorno
cp .env.example .env
# editar .env si es necesario

# 3. Levantar stack
docker compose up -d --build

# 4. Inicializar BD
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "IF DB_ID('PoluxImportDB') IS NULL CREATE DATABASE PoluxImportDB"
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m scripts.seed_data
docker compose exec -T backend python -m scripts.test_data

# 5. Abrir http://localhost:5173
```

> 💡 **Opcional**: existe un `Makefile` con atajos (`make up`, `make migrate`,
> `make seed`, etc.) para quienes tengan `make` instalado.

---

## 6. Credenciales de acceso

Los usuarios se crean automáticamente con `python -m scripts.seed_data`.

| Email | Contraseña | Rol | Acceso |
|---|---|---|---|
| `admin@poluximport.pe` | `Admin123!` | **ADMIN** | Todo el sistema |
| `operador@poluximport.pe` | `Oper123!` | **OPERADOR** | Pedidos, alertas, casos, imprevistos, entregas, comunicaciones |
| `gerente@poluximport.pe` | `Ger123!` | **GERENTE** | Solo Dashboard (lectura) |

> ⚠️ **Estas credenciales son SOLO para desarrollo.** Antes de cualquier
> despliegue en producción, cámbialas (ver `README-DEPLOY.md`).

### Permisos por rol

| Módulo | ADMIN | OPERADOR | GERENTE |
|---|---|---|---|
| Dashboard / KPIs | ✅ Lectura | ❌ | ✅ Lectura |
| Pedidos | ✅ | ✅ | ❌ |
| Completar hitos | ✅ | ✅ | ❌ |
| Casos / Imprevistos | ✅ | ✅ | ❌ |
| Alertas | ✅ | ✅ | ❌ |
| Entregas | ✅ | ✅ | ❌ |
| Comunicaciones | ✅ | ✅ | ❌ |
| Usuarios | ✅ CRUD | ❌ | ❌ |
| Reglas / Catálogos | ✅ CRUD | ❌ | ❌ |
| Operaciones (run-rules, sync-facts) | ✅ | ❌ | ❌ |

---

## 7. URLs del sistema

| Servicio | URL | Descripción |
|---|---|---|
| **Frontend** | http://localhost:5173 | Aplicación web (login) |
| Backend API | http://localhost:8000 | Base de la API |
| **Swagger** | http://localhost:8000/api/v1/docs | Documentación interactiva de endpoints |
| Health app | http://localhost:8000/api/v1/health | Estado de la aplicación |
| Health BD | http://localhost:8000/api/v1/health/db | Estado de la conexión a SQL Server |
| SQL Server | `localhost:1433` | Usuario `sa`, password del `.env` |

### Conectarse a SQL Server con cliente externo

- **Azure Data Studio** (gratis): [descargar](https://azure.microsoft.com/en-us/products/data-studio)
- **DBeaver** (gratis): [descargar](https://dbeaver.io/download/)

Configuración:
```
Servidor:      localhost,1433
Autenticación: SQL Login
Usuario:       sa
Contraseña:    <MSSQL_SA_PASSWORD del .env>
Database:      PoluxImportDB
Encrypt:       Optional (marcar "Trust Server Certificate")
```

---

## 8. Comandos útiles

### Ciclo de vida

```cmd
:: Levantar
docker compose up -d

:: Ver estado
docker compose ps

:: Ver logs en tiempo real
docker compose logs -f

:: Ver logs solo del backend
docker compose logs -f backend

:: Bajar (conserva datos)
docker compose down

:: Bajar y borrar BD (⚠️ reset completo)
docker compose down -v
```

### Backend

```cmd
:: Shell interactiva
docker compose exec backend bash

:: Correr pruebas
docker compose exec backend pytest -q

:: Audit: ¿todos los módulos importan?
docker compose exec backend python -m scripts.verify_modules

:: Verificar KPIs (vista vs SQL operacional)
docker compose exec backend python -m scripts.verify_kpis

:: Ejecutar motor de reglas manualmente
curl -X POST http://localhost:8000/api/v1/admin/run-rules -H "Authorization: Bearer <TOKEN>"

:: Procesar outbox (envío dry-run de mensajes pendientes)
curl -X POST http://localhost:8000/api/v1/outbox/run -H "Authorization: Bearer <TOKEN>"
```

### Frontend

```cmd
:: Tests unitarios
docker compose exec frontend npm test

:: Tests E2E (Playwright)
docker compose exec frontend npm run e2e
```

### SQL Server

```cmd
:: Consola sqlcmd interactiva
docker compose exec db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2025"

:: Consulta puntual
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2025" -d PoluxImportDB -Q "SELECT COUNT(*) FROM pedido;"
```

### Reset completo (empezar de cero)

```cmd
docker compose down -v
docker compose up -d --build
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2025" -Q "CREATE DATABASE PoluxImportDB"
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m scripts.seed_data
docker compose exec -T backend python -m scripts.test_data
```

---

## 9. Arquitectura y módulos

### Estructura del backend

```
backend/
├── app/
│   ├── core/           # Config, logging, security (JWT), deps, rate limit
│   ├── db/             # Session SQLAlchemy + Base declarativa
│   ├── models/         # ORM (pedido, item_hito, entrega, etc.) + modelo dimensional
│   ├── schemas/        # Pydantic v2 (validación request/response)
│   ├── services/       # Lógica de negocio (SOLID)
│   │   ├── pedido_service.py       # Consulta pedidos + recomputar estado
│   │   ├── hito_service.py         # Marcar hitos + detección de atrasos
│   │   ├── entrega_service.py      # Entregas (regla inviolable de parcial)
│   │   ├── rule_engine.py          # Motor de reglas (9 reglas idempotentes)
│   │   ├── agent_service.py        # Agente IA (clasifica, redacta, escala)
│   │   ├── llm_provider.py         # Mock + OpenAI-compatible
│   │   ├── whatsapp_service.py     # Meta Graph API
│   │   ├── outbox_worker.py        # Despacha comunicaciones PENDING
│   │   ├── fact_sync_service.py    # ETL a modelo dimensional
│   │   └── kpi_service.py          # Series temporales + validación SQL
│   └── api/v1/         # 19 routers REST
├── alembic/            # 12 migraciones (0001-0012)
├── scripts/            # seed_data, test_data, verify_modules, run_worker
└── tests/              # ~20 archivos de pruebas Pytest
```

### Estructura del frontend

```
frontend/
├── src/
│   ├── api/            # Cliente HTTP tipado por dominio
│   ├── auth/           # AuthContext + guards por rol
│   ├── components/     # DataTable, StatusBadge, FilterBar, KpiChart, etc.
│   ├── pages/          # Login, Dashboard, Pedidos, Entregas, Alertas, Admin
│   └── types/          # Tipos TypeScript alineados con schemas Pydantic
├── e2e/                # Playwright (login, entrega-parcial, dashboard)
└── src/test/           # Vitest + RTL
```

### Endpoints principales

```
POST   /api/v1/auth/login
GET    /api/v1/auth/me

GET    /api/v1/pedidos                          # Listar con filtros
GET    /api/v1/pedidos/{id}/full                # Pedido + ítems + hitos
PATCH  /api/v1/items/{id}/estado                # Cambiar estado de ítem
POST   /api/v1/hitos/{id}/completar             # Completar un hito

POST   /api/v1/entregas                         # Crear entrega (completa/parcial)
POST   /api/v1/entregas/{id}/completar          # Conformidad por ítem

GET    /api/v1/casos                            # Bandeja (ADMIN: todos; OPERADOR: asignados + libres)
POST   /api/v1/casos                            # Crear caso
GET    /api/v1/casos/{id}                       # Ficha del caso
POST   /api/v1/casos/{id}/responder             # Responder al cliente por Telegram
POST   /api/v1/casos/{id}/cerrar                # Cerrar caso
POST   /api/v1/casos/{id}/reasignar             # Asignar/reasignar (ADMIN) o liberar (OPERADOR)
PATCH  /api/v1/casos/{id}                       # Actualizar (1ª acción, estado)

GET    /api/v1/alertas                          # Alertas abiertas
PATCH  /api/v1/alertas/{id}/atender             # Marcar atendida

POST   /api/v1/agent/messages/incoming          # Simular mensaje al agente IA
GET    /api/v1/agent/metrics                    # Métricas del agente
GET    /api/v1/agent/chats                      # Contestador: chats visibles por rol
GET    /api/v1/agent/thread?pedido_id=          # Hilo de conversación (solo CLIENTE por defecto)
POST   /api/v1/agent/human-reply                # Respuesta humana sin caso (ADMIN)

GET    /api/v1/dashboard/resumen                # 7 KPIs actuales
GET    /api/v1/kpis/{codigo}/serie              # Serie temporal filtrable
GET    /api/v1/kpis/validacion                  # SQL reproducible por KPI

POST   /api/v1/webhooks/whatsapp                # (Meta) verificar/recibir
POST   /api/v1/outbox/run                       # Forzar despacho outbox
POST   /api/v1/admin/run-rules                  # Forzar motor de reglas
POST   /api/v1/admin/sync-facts                 # Forzar ETL dimensional
```

Lista completa en **http://localhost:8000/api/v1/docs**.

---

## 10. Fixes aplicados durante el setup

Estos fixes **ya están en el código del repositorio**. Se documentan aquí
para que quede claro qué se cambió respecto a la versión original de las
especificaciones y por qué.

### 10.1 SQL Server — cascadas múltiples (error 1785)

**Síntoma**: `Introducing FOREIGN KEY constraint ... may cause cycles or multiple cascade paths`

**Causa**: tablas con varias FKs `ON DELETE SET NULL` hacia la misma tabla destino.

**Fix**:
- `base_mixins.py`: las FKs `created_by_id` / `updated_by_id` a `usuario` **sin** `ondelete`.
- `Usuario` (en `core.py`): solo hereda `TimestampMixin` (no `AuditUserMixin`) para evitar auto-referencia doble.
- `comms.py` y `delivery.py`: FKs hacia `usuario` **sin** `ondelete`. Ciclo `Comunicacion ↔ CasoEscalamiento` resuelto con `NO ACTION`.
- Tablas que cascadean desde `pedido` (alerta, imprevisto) tienen FK a `pedido_item` sin `ondelete` (evita ruta extra `pedido → pedido_item → alerta`).

### 10.2 SQL Server — `RESTRICT` no soportado (error 156)

**Síntoma**: `Incorrect syntax near the keyword 'RESTRICT'`

**Fix**: reemplazado `ondelete="RESTRICT"` por `ondelete="NO ACTION"` en:
- `Contrato.cliente_id`
- `Pedido.cliente_id`
- `ItemHito.hito_id`
- `EntregaItem.pedido_item_id`

### 10.3 Migraciones 0003 y 0004 — columnas duplicadas (error 2705)

**Síntoma**: `Column name 'intentos_envio' in table 'comunicacion' is specified more than once`

**Causa**: el modelo `Comunicacion` ya incluye las columnas de outbox, pero
la migración 0003 intentaba agregarlas de nuevo.

**Fix**: migraciones `0003` y `0004` hechas **idempotentes** con `IF COL_LENGTH(...) IS NULL`.

### 10.4 passlib + bcrypt 4.1 — incompatibilidad

**Síntoma**: `ValueError: password cannot be longer than 72 bytes` al hashear

**Causa**: `passlib 1.7.4` es incompatible con `bcrypt >= 4.1`.

**Fix**: eliminado `passlib`, usado `bcrypt` directamente en `app/core/security.py`.

### 10.5 SQL Server — `IS 1` vs `= 1` (error 102)

**Síntoma**: `Incorrect syntax near '1'`

**Causa**: SQLAlchemy genera `col IS 1` para `.is_(True)`, inválido en SQL Server.

**Fix**: reemplazados todos los `.is_(True)` / `.is_(False)` por `== True` / `== False`.
Script automatizado en `backend/scripts/fix_is_true.py`.

### 10.6 `EntregaRead` sin items

**Síntoma**: el frontend no podía completar conformidad de entregas parciales.

**Fix**: añadido `items: list[EntregaItemRead]` al schema `EntregaRead` y
eager-load con `selectinload` en `GET /entregas`.

---

## 11. Troubleshooting

### `make` no se reconoce en Windows

No instales nada: usa `docker compose` directamente (ver sección 8).

Si quieres `make`, instálalo con Chocolatey:
```cmd
choco install make -y
```

### Puerto 1433 en uso

Tienes un SQL Server local en el puerto 1433. Dos opciones:

**Opción A** (recomendada): cambiar el puerto del contenedor.

Edita `docker-compose.yml`:
```yaml
services:
  db:
    ports:
      - "14330:1433"   # antes: "1433:1433"
```

Y en `.env`:
```env
DB_PORT=14330
```

**Opción B**: detener tu SQL Server local mientras trabajas en el proyecto.

### `db` no pasa a `healthy`

Ver logs:
```cmd
docker compose logs db
```

Causas típicas:
- `MSSQL_SA_PASSWORD` no cumple la política → cámbiala.
- Puerto 1433 ocupado → ver fix anterior.
- RAM insuficiente → libera memoria o aumenta el límite de Docker Desktop.

### `docker compose exec backend` falla porque el contenedor está en bucle

Ver logs:
```cmd
docker compose logs --tail=50 backend
```

Busca `ModuleNotFoundError` o `ImportError` → falta un archivo del repo.
Ejecuta la auditoría:
```cmd
docker compose run --rm --no-deps backend python -m scripts.verify_modules
```

### Telegram no responde

Confirma que el polling esté activo y que no exista un webhook configurado:

```cmd
docker compose ps telegram_poll
docker compose logs --tail=100 telegram_poll
docker compose exec -T telegram_poll python -c "from app.services.telegram_service import TelegramService; print(TelegramService().get_webhook_info())"
```

El resultado esperado del webhook contiene `url: ''`. Si los logs muestran
`Invalid object name 'coordinacion_entrega'`, faltan migraciones:

```cmd
docker compose exec -T backend alembic upgrade head
docker compose restart telegram_poll
```

### Login falla con "Credenciales inválidas"

Los usuarios demo no existen. Re-ejecuta:
```cmd
docker compose exec -T backend python -m scripts.seed_data
```

Verifica:
```cmd
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2025" -d PoluxImportDB -Q "SELECT email FROM usuario;"
```

### Reset completo

Si nada funciona:
```cmd
docker compose down -v
docker compose up -d --build
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2025" -Q "CREATE DATABASE PoluxImportDB"
docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m scripts.seed_data
docker compose exec -T backend python -m scripts.test_data
```

---

## 12. Estado del proyecto

| Fase | Estado |
|---|---|
| Fase 0 — Estructura del proyecto | ✅ Completa |
| Fase 1 — Base de datos (31 tablas + 7 vistas KPI) | ✅ Completa |
| Fase 2 — Backend y API (~50 endpoints) | ✅ Completa |
| Fase 3 — Motor de reglas (9 reglas + scheduler) | ✅ Completa |
| Fase 4 — Agente IA (Mock + OpenAI-compatible) | ✅ Completa |
| Fase 5 — WhatsApp + Email (con dry_run) | ✅ Completa |
| Fase 6 — Frontend de gestión | ✅ Completa |
| Fase 7 — Dashboard de KPIs | ✅ Completa |
| Fase 8 — Pruebas y despliegue | ✅ Completa |

### Criterios de aceptación verificados

- ✅ Pedido verificado recibe bienvenida automática.
- ✅ Seguimiento por ítem; estado del pedido refleja el ítem más atrasado.
- ✅ Hitos generan notificaciones consolidadas por pedido.
- ✅ Retrasos e imprevistos generan alertas y escalamientos.
- ✅ Reclamos se escalan sin intentar resolver automáticamente.
- ✅ **No se permite entrega parcial sin autorización humana registrada.**
- ✅ Cada comunicación, alerta y caso queda registrado con trazabilidad.
- ✅ No se cierra un pedido sin conformidad por ítem.
- ✅ Los 7 KPIs se calculan por SQL (nunca por IA).
- ✅ Los roles respetan sus permisos.
- ✅ El agente IA no inventa fechas ni toma decisiones reservadas a humanos.

### Lo que funciona en modo simulado (sin credenciales externas)

- **WhatsApp**: `WHATSAPP_DRY_RUN=true` → los mensajes se encolan y procesan
  pero no se envían a Meta. Los `wamid` son sintéticos (`dryrun.<uuid>`).
- **LLM**: `LLM_PROVIDER=mock` → clasificación determinista por keywords,
  ideal para desarrollo y pruebas.
- **Email**: `EMAIL_PROVIDER=mock` → no envía correos reales.

Para activar integraciones reales, ver `README-DEPLOY.md` y editar `.env`.

---

## 13. Próximos pasos

### Para continuar desarrollo

1. **Leer `PROGRESO_DESARROLLO.md`** — contiene el contexto completo de
   todas las fases, decisiones técnicas y archivos implementados.
2. **Ejecutar la suite de pruebas** para validar el estado:
   ```cmd
   docker compose exec backend pytest -q
   docker compose exec backend python -m scripts.verify_modules
   docker compose exec backend python -m scripts.verify_kpis
   ```
3. **Leer `README-DEPLOY.md`** para el despliegue en producción
   (gunicorn, nginx, backups, checklist de seguridad).

### Mejoras futuras sugeridas (post-piloto)

- Rate limiting distribuido (Redis) si se escala a N>1 backend.
- Integración de tracking de courier (automatiza actualización de hitos).
- Subida de evidencias fotográficas a S3/Blob para conformidad.
- Notificaciones en tiempo real (WebSocket) en la bandeja de alertas.
- Panel BI externo (Power BI) sobre las vistas `vw_kpi_*` si se prefiere.

### Para activar integraciones reales en desarrollo

**WhatsApp**:
```env
WHATSAPP_ENABLED=true
WHATSAPP_DRY_RUN=false
WHATSAPP_TOKEN=EAAG...
WHATSAPP_PHONE_NUMBER_ID=123456789
WHATSAPP_VERIFY_TOKEN=mi-token
WHATSAPP_APP_SECRET=app-secret
```
Configurar webhook público con ngrok: `ngrok http 8000` → en Meta usar
`https://<subdomain>.ngrok.io/api/v1/webhooks/whatsapp`.

**LLM real**:
```env
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

Tras cualquier cambio en `.env`:
```cmd
docker compose restart backend
```

---

## 📞 Contacto y soporte

- **Documentación técnica completa**: `PROGRESO_DESARROLLO.md`
- **Manual de despliegue productivo**: `README-DEPLOY.md`
- **Especificaciones del proyecto**: ver carpeta `docs/` si existe, o el plan
  original de desarrollo adjunto.

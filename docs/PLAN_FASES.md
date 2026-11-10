# Plan de fases — Polux Import · Fase Customers

> Hoja de ruta viva: diagnóstico, fases funcionales y estado de avance.
> Cada fase se marca completa al llegar a un estado estable **y** hacerse su commit.

**Fecha de creación:** 2026-11-09
**Última actualización:** 2026-11-10

---

## Tabla de contenido

1. [Diagnóstico: por qué el dashboard está vacío](#1-diagnóstico-por-qué-el-dashboard-está-vacío)
2. [Funciones incompletas o no implementadas](#2-funciones-incompletas-o-no-implementadas)
3. [Fases de ejecución](#3-fases-de-ejecución)
4. [Decisiones de diseño (doc + tecnologías)](#4-decisiones-de-diseño-doc--tecnologías)
5. [Estado de avance](#5-estado-de-avance)

---

## 1. Diagnóstico: por qué el dashboard está vacío

**El código del dashboard funciona correctamente** — el API responde, el
frontend pinta, las queries SQL corren. El problema es que **no hay eventos
que agregar**: los 7 KPIs solo miden cosas *terminadas* y en la BD de
demostración todo está a medias.

### Estado real de la BD (verificado con sqlcmd)

| Tabla | Registros | ¿Alimenta algún KPI? |
|---|---|---|
| `pedido` | 3 | — |
| `pedido_item` | 5 | — |
| `item_hito` | 25 → **0 en estado `COMPLETADO`** | ❌ Actualización al cliente necesita hitos completados |
| `entrega` | **0** | ❌ Los 3 KPIs de entregas → `SIN_DATOS` |
| `comunicacion` | **0** | ❌ Resolución automática → `SIN_DATOS` |
| `caso_escalamiento` | **0** | ❌ Tiempo respuesta escalados → `SIN_DATOS` |
| `imprevisto` | **0** | ❌ Resolución imprevistos → `por_tipo: []` |
| `fact_*` (dimensional) | **0** | El ETL no tiene nada que sincronizar |

`scripts/test_data.py` crea 3 pedidos **pero todos los hitos quedan
`PENDIENTE`** y no genera entregas/comunicaciones/casos. Los KPIs calculados
por SQL sobre eventos completados devuelven `null` → el frontend muestra `—`
y semáforo `SIN_DATOS`.

**No es un bug: es falta de datos de operación.** La solución es la Fase A.

---

## 2. Funciones incompletas o no implementadas

Barrido completo del código (20 routers, 16 servicios, 15 páginas).
**No hay ni un solo `TODO`/`FIXME`/`NotImplementedError`** — la deuda es
silenciosa.

### 🔴 Declarado pero NO funciona

| # | Función | Problema | Ubicación |
|---|---|---|---|
| B1 | Umbrales de KPI editables | La UI de Admin → Catálogos deja editar umbrales (`dim_kpi`), pero `kpis.py` los tiene **hardcodeados** y nunca lee la BD. Editar desde la UI **no tiene efecto**. | `backend/app/api/v1/kpis.py` (`_semaphore`) vs `catalogos.py` |
| B2 | Filtros del dashboard | El `FilterBar` ofrece producto/origen/operador, pero 4 de 7 series temporales **los ignoran en silencio**; en otra el filtro de operador se descarta. El usuario cree que filtra y no filtra. | `backend/app/services/kpi_service.py` (`_serie_*`) |

### 🟡 Backend listo, falta UI (endpoints huérfanos)

| # | Función | Endpoint listo | UI |
|---|---|---|---|
| C1 | **Agente IA (chat)** | `agent.py` (4 endpoints) | ✅ `/agente` (página con simulador, métricas y test de clasificación) |
| C2 | Crear casos | `POST /casos` | ✅ Botón **+ Nuevo caso** (modal) |
| C3 | Registrar imprevistos | `POST /imprevistos` | ✅ Botón **+ Nuevo imprevisto** (modal) |
| C4 | Enviar comunicaciones | `POST /comunicaciones` | ✅ Botón **+ Nuevo mensaje** (modal) |
| C5 | Cambiar estado de ítems | `PATCH /items/{id}/estado` | ❌ Sin UI (ni `api/items.ts`) |
| C6 | Procesar outbox manual | `POST /outbox/run` | ❌ Solo CLI |
| C7 | `GET /kpis/validacion` | `kpis.py` | ❌ Función muerta en ambos lados |

### 🔴 Bugs silenciosos descubiertos y corregidos en la Fase A

La ejecución real del sistema reveló 3 bugs que ningún `TODO` marcaba —
**el sistema llevaba roto desde el arranque** (el motor de reglas fallaba
cada 5 minutos con `rule_failed` en los logs):

| # | Bug | Síntoma | Fix |
|---|---|---|---|
| A1 | `comunicacion.whatsapp_message_id` era `UNIQUE` **nullable** — SQL Server solo permite un NULL en constraints UNIQUE | La 2ª comunicación en cola reventaba con error 23000 y **se caía toda la cadena del motor de reglas** (bienvenida, avisos, retrasos... jamás funcionaron) | Migración `0005`: índice único **filtrado** (`WHERE ... IS NOT NULL`) + modelo |
| A2 | El modelo `Comunicacion` no tenía la relación `plantilla` (solo la FK `plantilla_id`) | `outbox_worker` reventaba con `AttributeError: 'Comunicacion' object has no attribute 'plantilla'` → **ningún mensaje salía de la cola** | Relación añadida al modelo |
| A3 | `FactComunicacion` no tenía `operador_id` en el ORM, pero `fact_sync_service` lo pasaba y la migración 0004 ya creó la columna | `TypeError: 'operador_id' is an invalid keyword argument` → **el ETL de comunicaciones fallaba** | Columna añadida al modelo |

### 🟠 Suite de tests pre-existentemente rota (detectada en Fase A)

Los tests corren **contra la BD real** (`PoluxImportDB`) sin aislamiento:
~13 tests fallan con problemas pre-existentes (verificados contra baseline
sin los fixes): teardowns que borran `pedido` sin limpiar `comunicacion`
primero (conflicto FK), un test que pasa `datetime.date` donde se espera
`datetime` con tz, `GET /` devolviendo 404, y validación de firma de webhook
que no rechaza mensajes sin firma. **No bloquea la Fase A** (el sistema
funciona), pero requiere una fase dedicada → ver Fase T.

### 🟠 Integraciones simuladas (documentado, pero no reales)

- **WhatsApp** en `dry_run`, **Email** en `mock` — y **LLM ya NO es mock**:
  Gemini activo vía endpoint OpenAI-compatible (Fase G1), con el motor local
  (mock) como respaldo automático ante cuota/red.
- **Parámetros de plantillas WhatsApp** — `_extract_body_params` solo llena
  2 variables; el propio código dice *"en una iteración posterior"*.

### 🟡 Menores

- `README.md` **truncado** (10 líneas, bloque ```bash sin cerrar).
- Errores silenciados en frontend (`.catch(() => setRows([]))` en
  Comunicaciones, `.catch(() => {})` en filtros del dashboard).
- Paginación por heurística `rows.length < 50` en Comunicaciones (el
  endpoint no devuelve `total`).

### ✅ Módulos completos y sanos

Pedidos, hitos, entregas, alertas, reglas, catálogos, usuarios, auth,
webhooks, fact_sync, scheduler — todos con queries reales, cero respuestas
hardcodeadas.

---

## 3. Fases de ejecución

Se ejecutan en orden. **Cada fase termina con commit** cuando llega a un
estado estable (o al terminar un bloque de documentación).

| Fase | Contenido | Criterio de "estable" | Commit |
|---|---|---|---|
| **0. Plan** | Este documento (`docs/PLAN_FASES.md`) | Documento escrito | ✅ con Fase 1 |
| **A. Datos demo** | Script `scripts/demo_dashboard_data.py`: completar hitos, crear entregas (completa + parcial), casos, imprevistos, comunicaciones; correr `sync-facts` | `GET /dashboard/resumen` devuelve valores reales (no `SIN_DATOS`) en los 7 KPIs | ✅ |
| **Docs I** | `01-arquitectura.md`, `03-modelo-er.md`, `04-agente.md` | Los 3 documentos completos y con diagramas Mermaid renderizando | ✅ |
| **B. Arreglos KPI** | B1: umbrales leídos de `dim_kpi`. B2: filtros conectados en las 4 series (o documentados como no soportados) | Editar umbral en Admin cambia el semáforo; filtros afectan la serie | ✅ (2026-11-09) |
| **Docs II** | `02-flujos.md`, `05-manual-usuario.md` (con capturas), `06-api.md`, `README.md` reparado | Manual completo por rol con capturas del sistema poblado | ✅ |
| **C. UI del agente** | Página del agente IA + botones crear caso/imprevisto/comunicación (C1-C4) | Flujo completo desde la UI sin tocar la API a mano | ✅ |
| **T. Suite de tests** | Reparar los ~13 tests rotos: aislamiento de BD (o DB de test separada), orden de teardown por FKs, `datetime.date` vs datetime con tz, ruta `/`, validación de firma de webhook | `pytest -q` en verde | ✅ (2026-11-10) — 90 tests verdes y repetibles (2 corridas, cero residuo en BD) |
| **G1. Gemini activo** | Activar el LLM real (`LLM_PROVIDER=openai` + endpoint Gemini), con cortesía con la cuota (ventana RPM, reposo tras 429, modelo respaldo, motor local) y tests aislados de la cuota | `GET /agent/provider` → `gemini` y clasificación real verificada; suite en verde sin gastar cuota | ✅ (2026-11-10) |
| **G2. Simulador de chat WhatsApp** | Página que simula un chat de WhatsApp real: el agente recibe, clasifica, informa y toma acciones (caso/escalamiento); el humano responde desde la plataforma cuando el agente deriva | Flujo completo desde la UI (cliente → agente → escalamiento → respuesta humana) + manual y captura | ✅ (2026-11-10) — `GET /agent/chats`, `GET /agent/thread`, `POST /agent/human-reply`; página `/simulador` (bandeja, burbujas, modos Cliente/Asesor); 5 tests nuevos (103 en verde) + 3 tests de UI; e2e 14/14; captura 19 y manual §13; fix posterior de maquetación responsive (sin desbordamiento en 10 viewports, menú lateral adaptable en móvil) |
| **C2 (posterior)** | Canal Telegram (definido en `04-agente.md` durante Docs I) | Demo del agente respondiendo por Telegram | ⏳ futuro |

---

## 4. Decisiones de diseño (doc + tecnologías)

| Tema | Decisión | Justificación |
|---|---|---|
| **Audiencia del manual** | Usuarios del cliente (sin conocimientos técnicos) | Tareas paso a paso con capturas, sin jerga |
| **LLM** | **Gemini vía endpoint OpenAI-compatible** (`generativelanguage.googleapis.com/v1beta/openai`), `mock` como fallback | El código ya es OpenAI-compatible → activación solo con `.env`, sin tocar código. **Activado en Fase G1** con cortesía con la cuota (RPM/429) porque el plan gratuito limita ~5 llamadas/min y ~20/día |
| **Canal productivo** | WhatsApp Business Cloud API (ya implementado, `dry_run` → real) | Canal real de clientes en Perú |
| **Canal demo** | **Telegram Bot API** — *definido en documentación, implementación posterior* | Sin revisión de Meta, ideal para demostrar el agente en vivo |
| **Orquestación** | APScheduler + motor de reglas + outbox (interno) | Ya implementado, idempotente y trazable |
| **n8n** | **Descartado** | Duplicaría la orquestación interna, saca estado de la BD de auditoría, añade infraestructura. Reconsiderar solo si se pide edición visual de flujos o integración con herramientas externas (CRM, Sheets, email marketing) |
| **Diagramas** | Mermaid dentro de `docs/` | Versionables con el código, sin herramientas externas |
| **E-R** | Generado desde los modelos SQLAlchemy | Fuente única de verdad, no se desactualiza |

### Por qué el agente es "acotado" (mensaje central de `04-agente.md`)

El sistema tiene 3 capas:

```
PERCEPCIÓN                          RAZONAMIENTO                       ACTUACIÓN
──────────                          ─────────────                      ─────────
Scheduler (5 min)                ─┐
Mensajes entrantes (WhatsApp)    ─┼→  Reglas deterministas (9 reglas)  →  Outbox → Canal
Eventos de hitos/SLA             ─┤
                                 └→  LLM acotado (clasifica, redacta) →  Solo propone, NUNCA decide
                                                                         →  Escala a humano
```

**Decisiones reservadas a humanos por regla de negocio:** entrega parcial,
cierre de pedido, resolución de reclamos. El agente observa, clasifica,
redacta y escala — **la IA jamás inventa fechas ni calcula KPIs (eso es
100% SQL)**. Es una *feature*, no una limitación.

---

## 5. Estado de avance

| Fase | Estado |
|---|---|
| 0 · Plan (`docs/PLAN_FASES.md`) | ✅ Completo |
| A · Datos demo dashboard | ✅ Completo (2026-11-09) — 7 KPIs con valores reales + 3 bugs críticos corregidos (mig. 0005) |
| Docs I (arquitectura, E-R, agente) | ✅ Completo (2026-11-09) — `01`, `03`, `04` con Mermaid |
| B · Arreglos KPI (umbrales + filtros) | ✅ Completo (2026-11-09) — semáforos leen `dim_kpi` (probado: editar umbral cambia el semáforo); los 7 KPIs aplican producto/origen/operador |
| Docs II (flujos, manual, API, README) | ✅ Completada (2026-11-10) — `02-flujos.md`, `05-manual-usuario.md` (18 capturas), `06-api.md`, README; fixes rate-limit/CORS/KPI global |
| C · UI del agente (C1-C4) | ✅ Completa (2026-11-10) — página `/agente` + botones crear caso/imprevisto/comunicación; verificación e2e 10/10; build y tests del frontend en verde |
| T · Suite de tests | ✅ Completa (2026-11-10) — de 17 fallas + 2 errores a **90 tests en verde**; repetible sin residuo en BD (2 corridas con conteos idénticos) |
| G1 · Gemini activo | ✅ Completa (2026-11-10) — `LLM_PROVIDER=openai` + Gemini (`gemini-3.1-flash-lite`, respaldo `gemini-3.5-flash`); RateGuard (ventana RPM, reposo 429), motor local ante cualquier fallo; 8 tests nuevos (98 en verde) sin gastar cuota |
| G2 · Simulador de chat WhatsApp | ✅ Completa (2026-11-10) — `/simulador` con bandeja de chats, hilo en burbujas, modos Cliente/Asesor, tarjeta de decisión y banner de escalamiento; `POST /agent/human-reply` (auditoría HUMANO, caso → EN_PROCESO, agente cede el paso 10 min); e2e 14/14, captura 19, manual §13 |
| C2 · Canal Telegram | ⏳ Futuro |

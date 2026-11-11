# 06 · Referencia de la API

> Inventario completo de endpoints `Polux Import · Customers API v0.1.0`.
> Generado desde el OpenAPI real (`GET /api/v1/openapi.json`).

**Última actualización:** 2026-11-09
**Base URL:** `http://localhost:8000/api/v1`
**Swagger interactivo:** `http://localhost:8000/api/v1/docs`

---

## Tabla de contenido

1. [Autenticación](#1-autenticación)
2. [Roles y permisos](#2-roles-y-permisos)
3. [Convenciones y errores](#3-convenciones-y-errores)
4. [Endpoints por dominio](#4-endpoints-por-dominio)
5. [KPIs: códigos y parámetros](#5-kpis-códigos-y-parámetros)
6. [Webhooks (WhatsApp)](#6-webhooks-whatsapp)
7. [Ejemplos](#7-ejemplos)

---

## 1. Autenticación

Todos los endpoints (excepto `/health*`, `/webhooks/*` y el `GET` de
verificación del webhook) requieren un **Bearer token JWT**:

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email": "admin@poluximport.pe", "password": "Admin123!"}
```

Respuesta:

```json
{"access_token": "eyJ...", "token_type": "bearer"}
```

Uso posterior:

```http
GET /api/v1/pedidos
Authorization: Bearer eyJ...
```

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/auth/login` | Login → token JWT |
| GET | `/api/v1/auth/me` | Perfil y roles del usuario autenticado |

---

## 2. Roles y permisos

| Rol | Alcance |
|---|---|
| **ADMIN** | Todo: usuarios, catálogos, reglas, KPI umbrales, outbox, reglas manuales, clasificador del agente |
| **OPERADOR** | Operación diaria: pedidos, hitos, entregas, casos, imprevistos, comunicaciones, alertas |
| **GERENTE** | Solo lectura: dashboard, tableros |

Dependencias usadas por router: `require_admin` (usuarios, catálogos,
reglas-escritura, admin, outbox), `require_operador` (operación),
`require_gerente_o_admin` (dashboard). El token se valida **siempre en
el backend**, además de ocultar rutas en la UI.

---

## 3. Convenciones y errores

- **Formato de error** (FastAPI): `{"detail": "mensaje"}` o lista de
  validación `422`:

```json
{"detail": [{"type": "missing", "loc": ["query", "desde"], "msg": "Field required"}]}
```

| Código | Significado |
|---|---|
| `401` | Token ausente o inválido |
| `403` | Rol insuficiente |
| `404` | Recurso no encontrado |
| `409` | Conflicto de negocio (p. ej. hito ya completado, entrega parcial sin autorización) |
| `422` | Payload/query inválidos (validación Pydantic) |

- **Fechas** en UTC ISO-8601 (`2026-11-09T22:43:51`).
- **Enums** como strings en mayúsculas (`"PENDIENTE"`, `"WHATSAPP"`).
- **Auditoría:** toda respuesta incluye `created_at` / `updated_at`;
  los registros llevan `created_by_id` / `updated_by_id`.
- **Simulación:** los envíos por WhatsApp corren en `dry_run` por
  defecto (wamid sintético `dryrun.<uuid>`).

---

## 4. Endpoints por dominio

### Health

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/health` | Liveness de la aplicación | público |
| GET | `/health/db` | Liveness de la base de datos | público |

### Auth

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| POST | `/auth/login` | Login | público |
| GET | `/auth/me` | Perfil del usuario autenticado | cualquiera |

### Usuarios

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| POST | `/usuarios` | Crear usuario | ADMIN |
| GET | `/usuarios` | Listar usuarios | ADMIN |
| PATCH | `/usuarios/{usuario_id}` | Actualizar usuario | ADMIN |

### Pedidos

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/pedidos` | Listar pedidos (`estado`, `cliente_id`, `origen`, paginación) | OPERADOR+ |
| GET | `/pedidos/{pedido_id}` | Detalle de pedido (con ítems) | OPERADOR+ |
| GET | `/pedidos/{pedido_id}/full` | Pedido completo (ítems + hitos) | OPERADOR+ |
| GET | `/pedidos/{pedido_id}/timeline` | Línea de tiempo fusionada del pedido | OPERADOR+ |

**Línea de tiempo** (`GET /pedidos/{pedido_id}/timeline`): fusiona en una
sola lista ordenada por fecha (más reciente primero) las fuentes del
pedido — ingreso, hitos (completados/atrasados), mensajes, casos
(apertura, primera respuesta, cierre), imprevistos, entregas y alertas.
Solo lectura: no escribe datos ni dispara el motor de reglas.

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `incluir_mensajes` | bool | `false` | `false` = solo eventos clave (quejas/escalamientos, respuestas del asesor y avisos con plantilla); `true` = todos los mensajes e interacciones |
| `tipos` | string | — | Filtro por tipos separados por coma: `pedido,hito,mensaje,caso,imprevisto,entrega,alerta` (422 si hay tipos desconocidos) |
| `desde` / `hasta` | fecha ISO (UTC) | — | Ventana de fechas de los eventos |
| `limit` | int 1–500 | 200 | Máximo de eventos (los más recientes primero) |

La respuesta incluye `resumen` (mensajes, mensajes clave, hitos
atrasados, casos/imprevistos abiertos, alertas activas) y `eventos` con
`{fecha, tipo, titulo, detalle, criticidad, ref_tipo, ref_id, autor}`.

### Ítems

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| PATCH | `/items/{item_id}/estado` | Actualiza el estado de un ítem | OPERADOR |

### Hitos

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| POST | `/hitos/{item_hito_id}/completar` | Marcar hito completado (fecha real) | OPERADOR |
| GET | `/hitos/por-item/{pedido_item_id}` | Listar hitos de un ítem | OPERADOR+ |

### Entregas

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/entregas?pedido_id=` | Listar entregas de un pedido | OPERADOR+ |
| POST | `/entregas` | Crear entrega (COMPLETA o PARCIAL con autorización) | OPERADOR |
| POST | `/entregas/{entrega_id}/completar` | Completar con checklist de conformidad | OPERADOR |

### Casos

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/casos` | Listar casos de escalamiento | OPERADOR+ |
| POST | `/casos` | Crear caso manual | OPERADOR |
| PATCH | `/casos/{caso_id}` | Primera acción, cambio de estado, cierre | OPERADOR |

### Imprevistos

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/imprevistos` | Listar | OPERADOR+ |
| POST | `/imprevistos` | Registrar imprevisto | OPERADOR |
| PATCH | `/imprevistos/{imprevisto_id}` | Actualizar / resolver | OPERADOR |

### Comunicaciones

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/comunicaciones` | Historial (filtros: pedido, canal, dirección…) | OPERADOR+ |
| POST | `/comunicaciones` | Envío manual (queda en cola → outbox) | OPERADOR |

### Alertas

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/alertas` | Bandeja de alertas | OPERADOR+ |
| PATCH | `/alertas/{alerta_id}` | Cambiar estado | OPERADOR |
| PATCH | `/alertas/{alerta_id}/atender` | Marcar como atendida | OPERADOR |

### Reglas

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/reglas` | Listar parámetros de reglas | OPERADOR+ |
| PATCH | `/reglas/{regla_id}` | Editar umbral/parámetro | ADMIN |

### Catálogos

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET/POST | `/catalogos/hitos` | Catálogo de hitos | ADMIN |
| PATCH | `/catalogos/hitos/{hito_id}` | Editar hito | ADMIN |
| GET/POST | `/catalogos/sla` | SLA por hito (días) | ADMIN |
| PATCH | `/catalogos/sla/{sla_id}` | Editar SLA | ADMIN |
| GET/POST | `/catalogos/plantillas` | Plantillas de mensaje | ADMIN |
| PATCH | `/catalogos/plantillas/{plantilla_id}` | Editar plantilla | ADMIN |
| GET | `/catalogos/kpis` | Umbrales de los 7 KPIs (`dim_kpi`) | ADMIN |
| PATCH | `/catalogos/kpis/{kpi_id}` | Editar umbrales (cambia el semáforo al instante) | ADMIN |

### KPIs y dashboard

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/dashboard/resumen` | Snapshot de los 7 KPIs con semáforos | GERENTE/ADMIN |
| GET | `/kpis/{codigo}/serie` | Serie temporal con filtros | autenticado |
| GET | `/kpis/filtros/opciones` | Opciones de filtro (productos, orígenes, operadores) | autenticado |
| GET | `/kpis/validacion` | SQL de contraste manual por KPI | autenticado |
| GET | `/kpis/actualizacion-cliente` … `/entregas-parciales` | Los 7 KPIs individuales (ver §5) | autenticado |

### Agente IA

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| POST | `/agent/messages/incoming` | Procesa un mensaje entrante (simulación local) | autenticado |
| GET | `/agent/provider` | Proveedor LLM activo (mock / gemini) | autenticado |
| GET | `/agent/metrics` | Métricas agregadas del agente | autenticado |
| GET | `/agent/chats` | Bandeja del simulador: un chat por pedido (cliente, preview, caso abierto, asesor reciente) | autenticado |
| GET | `/agent/thread?pedido_id=` | Hilo de conversación de un pedido (mensajes con clasificación y caso) | autenticado |
| POST | `/agent/human-reply` | Responde como persona (asesor) en el hilo; marca el caso EN_PROCESO y el agente cede el paso | OPERADOR |
| POST | `/agent/test/classify` | Clasifica un texto sin ejecutar el flujo (degrada al motor local si el LLM cae) | ADMIN |

### Operación manual (admin)

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| POST | `/admin/run-rules` | Ejecuta el motor de reglas ahora | ADMIN |
| POST | `/admin/sync-facts` | Sincroniza el modelo dimensional ahora | ADMIN |
| POST | `/outbox/run` | Despacha la cola de comunicaciones ahora | ADMIN |

### Webhooks

| Método | Ruta | Descripción | Rol |
|---|---|---|---|
| GET | `/webhooks/whatsapp` | Verificación del webhook (token Meta) | público |
| POST | `/webhooks/whatsapp` | Recepción de mensajes/eventos | firma requerida |

---

## 5. KPIs: códigos y parámetros

### Códigos (`codigo` para `/kpis/{codigo}/serie`)

| Código | Unidad | Sentido | KPI individual |
|---|---|---|---|
| `FREQ_ACTUALIZACION_CLIENTE` | % | mayor_mejor | `/kpis/actualizacion-cliente` |
| `TASA_RESOLUCION_AUTOMATICA` | % | mayor_mejor | `/kpis/resolucion-automatica` |
| `TIEMPO_RESPUESTA_ESCALADOS` | horas | menor_mejor | `/kpis/tiempo-respuesta-escalados` |
| `TIEMPO_RESOLUCION_IMPREVISTOS` | días | menor_mejor | `/kpis/resolucion-imprevistos` |
| `ENTREGAS_A_TIEMPO` | % | mayor_mejor | `/kpis/entregas-a-tiempo` |
| `ENTREGAS_SIN_OBSERVACIONES` | % | mayor_mejor | `/kpis/entregas-sin-observaciones` |
| `PCT_ENTREGAS_PARCIALES` | % | menor_mejor | `/kpis/entregas-parciales` |

Los **umbrales de semáforo** (verde/ámbar/rojo) viven en `dim_kpi` y se
editan con `PATCH /catalogos/kpis/{id}` — la respuesta de cada KPI
incluye `"umbrales": {"optimo": …, "alerta": …}`.

Los valores de los KPIs se calculan exclusivamente en las vistas
`vw_kpi_*` sobre las tablas de hechos `fact_*` y dimensiones `dim_*`.
El proceso `fact_sync` actualiza esas tablas desde la operación; por eso
los endpoints del dashboard no consultan directamente las tablas
operacionales.

### Parámetros de la serie

| Parámetro | Requerido | Descripción |
|---|---|---|
| `desde` | ✅ | Fecha inicio `YYYY-MM-DD` |
| `hasta` | ✅ | Fecha fin `YYYY-MM-DD` |
| `granularidad` | no (`mes`) | `dia` \| `semana` \| `mes` |
| `producto_id` | no | Filtra por producto (subconsulta sobre `pedido_item`) |
| `origen` | no | `STOCK_TRUJILLO` \| `IMPORTACION` |
| `operador_id` | no | Semántica por KPI: columna propia (hitos/comunicaciones), responsable del caso, del imprevisto o de la entrega |

Respuesta:

```json
{
  "granularidad": "mes",
  "tipo": "porcentaje",
  "serie": [
    {"periodo": "2026-11", "etiqueta": "Nov 2026", "valor": 90.0,
     "total": 10, "numerador": 9.0}
  ]
}
```

`valor = null` cuando `total = 0` (sin datos en ese periodo).

---

## 6. Webhooks (WhatsApp)

**Verificación (GET):** Meta envía `hub.mode`, `hub.verify_token` y
`hub.challenge`; el token debe coincidir con `WHATSAPP_VERIFY_TOKEN`.

**Eventos (POST):** payload de Meta con `entry[].changes[].messages[]`.
Validación de firma con `WHATSAPP_APP_SECRET` (header
`X-Hub-Signature-256`). Cada mensaje se convierte en una comunicación
ENTRANTE que el agente clasifica (flujo 3 de [`02-flujos.md`](02-flujos.md)).

---

## 7. Ejemplos

### Login y llamada autenticada

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@poluximport.pe","password":"Admin123!"}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s http://localhost:8000/api/v1/dashboard/resumen \
  -H "Authorization: Bearer $TOKEN"
```

### Serie con filtros

```bash
curl -s "http://localhost:8000/api/v1/kpis/ENTREGAS_A_TIEMPO/serie?desde=2026-01-01&hasta=2026-12-31&granularidad=mes&origen=IMPORTACION" \
  -H "Authorization: Bearer $TOKEN"
```

### Ejecutar reglas + ETL a mano (ADMIN)

```bash
curl -s -X POST http://localhost:8000/api/v1/admin/run-rules  -H "Authorization: Bearer $TOKEN"
curl -s -X POST http://localhost:8000/api/v1/admin/sync-facts -H "Authorization: Bearer $TOKEN"
curl -s -X POST http://localhost:8000/api/v1/outbox/run       -H "Authorization: Bearer $TOKEN"
```

### Simular un mensaje del cliente (agente)

```bash
curl -s -X POST http://localhost:8000/api/v1/agent/messages/incoming \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"pedido_id": 1, "contenido": "¿Dónde está mi pedido?"}'
```

---

**Anterior:** [`05-manual-usuario.md`](05-manual-usuario.md) ·
**Volver al plan:** [`PLAN_FASES.md`](PLAN_FASES.md)

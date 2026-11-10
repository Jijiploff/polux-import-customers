# 03 · Modelo entidad-relación

> 31 tablas en `PoluxImportDB`: 17 operacionales, 11 dimensionales
> (KPIs) y 3 de acceso/auditoría. Generado desde los modelos SQLAlchemy
> y verificado contra las FK reales de la BD.

**Última actualización:** 2026-11-09
**Fuente de verdad:** `backend/app/models/` (+ migraciones `0001`–`0005`)

---

## Tabla de contenido

1. [Convenciones](#1-convenciones)
2. [Esquema operacional](#2-esquema-operacional)
3. [Esquema de acceso y auditoría](#3-esquema-de-acceso-y-auditoría)
4. [Esquema dimensional (KPIs)](#4-esquema-dimensional-kpis)
5. [Catálogo de estados por tabla](#5-catálogo-de-estados-por-tabla)
6. [Reglas de integridad destacadas](#6-reglas-de-integridad-destacadas)

---

## 1. Convenciones

- **PK** `id INT IDENTITY` en todas las tablas.
- **Auditoría:** casi todas las tablas llevan `created_at`, `updated_at`,
  `created_by_id`, `updated_by_id` → `usuario` (no dibujados en los
  diagramas por claridad, pero existen).
- **Enums:** en BD son `NVARCHAR` con `CHECK`; en Python son `enum.Enum`
  (ver catálogo de estados en §5).
- **Borrado:** sin `ON DELETE CASCADE` entre pedidos y sus dependientes
  directos (restricción de SQL Server: una tabla no puede cascadear dos
  veces en la misma cadena) — el borrado se hace en orden desde el
  servicio o queda en `NO ACTION`.

---

## 2. Esquema operacional

Ciclo de vida: **cliente → contrato → pedido → ítems → hitos → entrega**,
con **comunicaciones, alertas, imprevistos y casos** acompañando al pedido.

```mermaid
erDiagram
    CLIENTE ||--o{ CONTRATO : "tiene"
    CLIENTE ||--o{ PEDIDO : "compra"
    CONTRATO ||--o{ PEDIDO : "origina"
    PEDIDO ||--o{ PEDIDO_ITEM : "contiene"
    PRODUCTO ||--o{ PEDIDO_ITEM : "es"
    PEDIDO_ITEM ||--o{ ITEM_HITO : "avanza por"
    HITO_CATALOGO ||--o{ ITEM_HITO : "define"
    HITO_CATALOGO ||--o{ SLA_HITO : "tiene SLA"

    CLIENTE {
        int id PK
        string razon_social
        string tipo_documento
        string numero_documento
        string telefono
        string email
        bool consentimiento_comunicaciones
    }
    CONTRATO {
        int id PK
        int cliente_id FK
        string codigo
        date fecha_inicio
        string estado
    }
    PRODUCTO {
        int id PK
        string sku
        string nombre
        string categoria
    }
    PEDIDO {
        int id PK
        string codigo
        int cliente_id FK
        int contrato_id FK
        string estado_ingreso
        string estado_actual
        datetime fecha_ingreso
        datetime fecha_prometida
        string modalidad_entrega
        bool consentimiento_comunicaciones
    }
    PEDIDO_ITEM {
        int id PK
        int pedido_id FK
        int producto_id FK
        string origen
        string estado
        string modelo
        string color
        string capacidad
        int cantidad
    }
    HITO_CATALOGO {
        int id PK
        string codigo
        string nombre
        int orden
    }
    SLA_HITO {
        int id PK
        int hito_id FK
        int dias_maximos
    }
    ITEM_HITO {
        int id PK
        int pedido_item_id FK
        int hito_id FK
        string estado
        datetime fecha_prevista
        datetime fecha_real
        datetime fecha_notificacion
        bool notificado_cliente
        int dias_atraso
    }
```

### Entregas y conformidad

```mermaid
erDiagram
    PEDIDO ||--o{ ENTREGA : "se entrega en"
    ENTREGA ||--o{ ENTREGA_ITEM : "incluye"
    ENTREGA_ITEM ||--o{ CONFORMIDAD : "verifica"
    PEDIDO_ITEM ||--o{ ENTREGA_ITEM : "es entregado en"

    ENTREGA {
        int id PK
        int pedido_id FK
        string tipo "COMPLETA | PARCIAL"
        string modalidad
        string estado "PROGRAMADA…FALLIDA"
        datetime fecha_programada
        datetime fecha_real
        int autorizada_por_id FK "solo parcial: quién autoriza"
        datetime fecha_autorizacion
        string motivo_parcial "por qué (obligatorio en parcial)"
    }
    ENTREGA_ITEM {
        int id PK
        int entrega_id FK
        int pedido_item_id FK
    }
    CONFORMIDAD {
        int id PK
        int entrega_item_id FK
        bool checklist_caja_sellada
        bool checklist_modelo_ok
        bool checklist_color_ok
        bool checklist_capacidad_ok
        bool checklist_imei_ok
        bool checklist_accesorios_ok
        string resultado "CONFORME | CON_OBSERVACIONES"
        string observaciones
        string evidencias_urls
        int registrado_por_id FK
    }
```

> **Regla inviolable:** una entrega `PARCIAL` exige `autorizada_por_id`,
> `fecha_autorizacion` y `motivo_parcial` (validado en servicio **y** por
> `CHECK ck_entrega_parcial_requiere_autorizacion` en BD).

### Comunicación, alertas, imprevistos y casos

```mermaid
erDiagram
    PEDIDO ||--o{ COMUNICACION : "comunica"
    PLANTILLA_MENSAJE ||--o{ COMUNICACION : "renderiza"
    COMUNICACION ||--o{ CASO_ESCALAMIENTO : "origina"
    CASO_ESCALAMIENTO ||--o{ COMUNICACION : "asocia caso"
    PEDIDO ||--o{ CASO_ESCALAMIENTO : "escala"
    PEDIDO ||--o{ ALERTA : "genera"
    ITEM_HITO ||--o{ ALERTA : "dispara"
    PEDIDO ||--o{ IMPREVISTO : "sufre"
    PEDIDO_ITEM ||--o{ IMPREVISTO : "afecta a"

    PLANTILLA_MENSAJE {
        int id PK
        string codigo "BIENVENIDA, AVISO_HITO…"
        string nombre
        string canal
        string cuerpo "con {placeholders}"
    }
    COMUNICACION {
        int id PK
        int pedido_id FK
        int pedido_item_id FK
        int plantilla_id FK
        int caso_id FK
        string direccion "ENTRANTE | SALIENTE"
        string canal "WHATSAPP | EMAIL | WEB"
        string contenido
        string intencion_detectada "por el agente"
        string sentimiento "NEUTRO|POSITIVO|NEGATIVO"
        string autor "CLIENTE | AGENTE | SISTEMA | USUARIO"
        string estado_entrega "PENDING|SENT|FAILED…"
        string whatsapp_message_id "wamid (único si no es NULL)"
        datetime fecha
        bool escalado
    }
    CASO_ESCALAMIENTO {
        int id PK
        int pedido_id FK
        int comunicacion_origen_id FK
        string motivo "RECLAMO, RETRASO_CRITICO…"
        string prioridad "ALTA|MEDIA|BAJA"
        datetime fecha_apertura
        datetime fecha_primera_accion "primer contacto humano"
        int responsable_id FK
        string estado "ABIERTO|EN_PROCESO|RESUELTO|CERRADO"
        datetime fecha_cierre
    }
    ALERTA {
        int id PK
        int pedido_id FK
        int pedido_item_id FK
        int item_hito_id FK
        string tipo "RETRASO_LEVE|RETRASO_CRITICO|IMPREVISTO…"
        string severidad "INFO|LEVE|CRITICA"
        string estado "ABIERTA|ATENDIDA"
        datetime fecha_deteccion
        datetime fecha_atencion
    }
    IMPREVISTO {
        int id PK
        int pedido_id FK
        int pedido_item_id FK
        string tipo "ADUANERO|OPERATIVO|PROVEEDOR|LOGISTICO|OTRO"
        string descripcion
        datetime fecha_deteccion
        datetime fecha_resolucion "obligatorio si RESUELTO"
        string resolucion
        string estado "ABIERTO|EN_PROCESO|RESUELTO"
        int responsable_id FK
    }
    REGLA_NEGOCIO {
        int id PK
        string codigo
        string parametro
        string valor
        bool vigente
    }
```

> **Nota sobre el vínculo caso↔comunicación:** es bidireccional a
> propósito. `comunicacion.origen → caso` registra *qué mensaje originó el
> caso*; `caso → comunicacion.caso_id` marca *qué caso gestiona una
> comunicación* (así el motor de reglas evita duplicados).

---

## 3. Esquema de acceso y auditoría

```mermaid
erDiagram
    ROL ||--o{ USUARIO_ROL : "asigna"
    USUARIO ||--o{ USUARIO_ROL : "tiene"

    ROL {
        int id PK
        string codigo "ADMIN | OPERADOR | GERENTE"
        string nombre
    }
    USUARIO {
        int id PK
        string email UK
        string password_hash
        string nombre_completo
        bool activo
    }
    USUARIO_ROL {
        int usuario_id PK_FK
        int rol_id PK_FK
    }
```

---

## 4. Esquema dimensional (KPIs)

Separado del operacional: los KPIs leen **solo** `fact_*` (hechos ya
sincronizados por `fact_sync` cada 5 min), nunca transaccionales.

```mermaid
erDiagram
    DIM_TIEMPOTIEMPO ||--o{ FACT_HITO_PEDIDO : ""
    DIM_TIEMPOTIEMPO ||--o{ FACT_COMUNICACION : ""
    DIM_TIEMPOTIEMPO ||--o{ FACT_ESCALAMIENTO : ""
    DIM_TIEMPOTIEMPO ||--o{ FACT_IMPREVISTO : ""
    DIM_TIEMPOTIEMPO ||--o{ FACT_ENTREGA : ""
    DIM_CANAL ||--o{ FACT_COMUNICACION : ""
    DIM_PRODUCTO ||--o{ FACT_HITO_PEDIDO : ""
    DIM_HITO ||--o{ FACT_HITO_PEDIDO : ""
    DIM_TIPO_IMPREVISTO ||--o{ FACT_IMPREVISTO : ""
    PRODUCTO ||--o| DIM_PRODUCTO : "espejo"
    HITO_CATALOGO ||--o| DIM_HITO : "espejo"

    DIM_TIEMPOTIEMPO {
        int id PK
        date fecha
        int anio
        int mes
        int dia
        int semana
        string dia_semana
    }
    DIM_CANAL {
        int id PK
        string codigo
    }
    DIM_PRODUCTO {
        int id PK
        int producto_id FK
        string sku
        string nombre
    }
    DIM_HITO {
        int id PK
        int hito_id FK
        string codigo
        string nombre
    }
    DIM_TIPO_IMPREVISTO {
        int id PK
        string codigo
    }
    DIM_KPI {
        int id PK
        string codigo "FREQ_ACTUALIZACION_CLIENTE…"
        string nombre
        string nivel
        int umbral_verde
        int umbral_ambar
        int umbral_rojo
    }
    FACT_HITO_PEDIDO {
        int id PK
        int tiempo_id FK
        int hito_id FK
        int producto_id FK
        int pedido_id
        bool notificado
        bool notificado_oportuno
        int dias_atraso
        string origen
        int operador_id
    }
    FACT_COMUNICACION {
        int id PK
        int tiempo_id FK
        int canal_id FK
        int comunicacion_id UK
        int pedido_id
        string direccion
        string autor
        bool escalado
        string sentimiento
        int operador_id
    }
    FACT_ESCALAMIENTO {
        int id PK
        int tiempo_id FK
        int caso_id
        int pedido_id
        int horas_respuesta
        string prioridad
    }
    FACT_IMPREVISTO {
        int id PK
        int tiempo_id FK
        int tipo_id FK
        int pedido_id
        int dias_resolucion
        string estado
    }
    FACT_ENTREGA {
        int id PK
        int tiempo_id FK
        int pedido_id
        int entrega_id
        string tipo
        bool a_tiempo
        bool con_observaciones
        string modalidad
    }
```

`dim_kpi` guarda los **umbrales de semáforo** de los 7 KPIs del
dashboard (verde/ámbar/rojo).

---

## 5. Catálogo de estados por tabla

| Tabla | Campo | Valores |
|---|---|---|
| `pedido` | `estado_actual` | `RECIBIDO` → `EN_PROCESO` → `LISTO_PARA_ENTREGA` → `EN_COORDINACION` → `ENTREGADO` → `CERRADO` / `CERRADO_CON_OBSERVACIONES` / `CANCELADO` |
| `pedido` | `estado_ingreso` | `PRIMER_PAGO_VERIFICADO`, `PAGO_COMPLETO_VERIFICADO` |
| `pedido_item` | `estado` | `PENDIENTE`, `EN_PROCESO`, `LISTO_PARA_ENTREGA`, `ENTREGADO`, `CON_OBSERVACIONES` |
| `item_hito` | `estado` | `PENDIENTE`, `EN_PROCESO`, `COMPLETADO`, `ATRASADO` |
| `entrega` | `tipo` | `COMPLETA`, `PARCIAL` |
| `entrega` | `estado` | `PROGRAMADA`, `EN_RUTA`, `ENTREGADA`, `FALLIDA`, `REPROGRAMADA` |
| `conformidad` | `resultado` | `CONFORME`, `CON_OBSERVACIONES` |
| `comunicacion` | `direccion` | `ENTRANTE`, `SALIENTE` |
| `comunicacion` | `canal` | `WHATSAPP`, `EMAIL`, `WEB` |
| `comunicacion` | `autor` | `CLIENTE`, `AGENTE`, `SISTEMA`, `USUARIO` |
| `comunicacion` | `estado_entrega` | `PENDING`, `SENT`, `SENT_EMAIL`, `FAILED_RETRY`, `FAILED` (NULL = entrante) |
| `caso_escalamiento` | `estado` | `ABIERTO`, `EN_PROCESO`, `RESUELTO`, `CERRADO` |
| `caso_escalamiento` | `motivo` | `RECLAMO`, `RETRASO_LEVE`, `RETRASO_CRITICO`, `IMPREVISTO`, `DAÑO`, `PRODUCTO_INCORRECTO`, `FALTA_RESPUESTA` |
| `imprevisto` | `tipo` | `ADUANERO`, `OPERATIVO`, `PROVEEDOR`, `LOGISTICO`, `OTRO` |
| `imprevisto` | `estado` | `ABIERTO`, `EN_PROCESO`, `RESUELTO` (exige `fecha_resolucion`) |
| `alerta` | `tipo` | `RETRASO_LEVE`, `RETRASO_CRITICO`, `IMPREVISTO`, `SILENCIO_CLIENTE`, `ESCALAMIENTO` |
| `alerta` | `estado` | `ABIERTA`, `ATENDIDA` |
| `pedido` | `modalidad_entrega` | `DOMICILIO`, `RECOJO` |
| `pedido_item` | `origen` | `STOCK_TRUJILLO`, `IMPORTACION` |

---

## 6. Reglas de integridad destacadas

1. **Entrega parcial autorizada** — `CHECK ck_entrega_parcial_requiere_autorizacion`:
   `tipo='PARCIAL'` ⇒ `autorizada_por_id`, `fecha_autorizacion` y
   `motivo_parcial` NO NULL.
2. **Imprevisto resuelto** — `fecha_resolucion` obligatoria en `RESUELTO`.
3. **wamid único filtrado** (migración `0005`) — índice único sobre
   `comunicacion.whatsapp_message_id` **solo cuando no es NULL**
   (SQL Server no admite varios NULL en UNIQUE; un `UNIQUE` simple
   rompía la cola de mensajes).
4. **Auditoría completa** — `created_by_id`/`updated_by_id` en casi todas
   las tablas operacionales.
5. **Sin cascadas dobles** — SQL Server rechaza cadenas de cascade
   (`pedido → pedido_item → X` cuando `X` también cascadea de `pedido`);
   por eso `caso_escalamiento.comunicacion_origen_id` y
   `comunicacion.caso_id` son `NO ACTION` (borrar requiere desvincular
   primero).

---

**Anterior:** [`01-arquitectura.md`](01-arquitectura.md) ·
**Siguiente:** [`04-agente.md`](04-agente.md)

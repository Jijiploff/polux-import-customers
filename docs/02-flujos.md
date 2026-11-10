# 02 · Flujos del negocio

> Los 8 flujos principales del sistema, diagramados con Mermaid.
> Audiencia: equipo de desarrollo y analistas.

**Última actualización:** 2026-11-09

---

## Tabla de contenido

1. [Registro de pedido e ingreso de pago](#1-registro-de-pedido-e-ingreso-de-pago)
2. [Seguimiento de hitos y avisos al cliente](#2-seguimiento-de-hitos-y-avisos-al-cliente)
3. [Mensaje entrante del cliente (agente)](#3-mensaje-entrante-del-cliente-agente)
4. [Entrega completa con conformidad](#4-entrega-completa-con-conformidad)
5. [Entrega parcial autorizada](#5-entrega-parcial-autorizada)
6. [Escalamiento de caso](#6-escalamiento-de-caso)
7. [Imprevisto (incidencia)](#7-imprevisto-incidencia)
8. [Comunicación saliente y actualización de KPIs](#8-comunicación-saliente-y-actualización-de-kpis)

---

## 1. Registro de pedido e ingreso de pago

```mermaid
flowchart TD
    A[Operador crea el pedido<br/>POST /pedidos] --> B[Estado_ingreso:<br/>PRIMER_PAGO_VERIFICADO]
    B --> C[Se generan ítems<br/>con su origen STOCK / IMPORTACIÓN]
    C --> D[Se generan los hitos del ítem<br/>según el catálogo + SLA]
    D --> E[Regla BIENVENIDA:<br/>mensaje de bienvenida en cola]
    E --> F[(pedido RECIBIDO / EN_PROCESO)]
    F --> G{¿Segundo pago?}
    G -->|Sí| H[estado_ingreso =<br/>PAGO_COMPLETO_VERIFICADO]
    G -->|No| F
    H --> F
```

**Notas:**
- Los hitos se crean automáticamente al crear el ítem
  (`item_hito` con `fecha_prevista` encadenada por SLA).
- `fecha_prometida` del pedido = mayor `fecha_prevista` de sus hitos.

---

## 2. Seguimiento de hitos y avisos al cliente

```mermaid
flowchart TD
    S[Scheduler cada 5 min] --> R{Reglas evaluadas}
    R --> A[Hito COMPLETADO sin notificar]
    A --> M1[Plantilla AVISO_HITO<br/>→ outbox → WhatsApp]
    A --> M1f[marca notificado_cliente<br/>fecha_notificacion]
    R --> B[Hito con fecha_prevista vencida]
    B --> T[registrar_atrasos:<br/>estado=ATRASADO, dias_atraso]
    T --> C{¿Atraso?}
    C -->|leve ≤ umbral| D[Alerta RETRASO_LEVE +<br/>plantilla RETRASO_LEVE]
    C -->|crítico > umbral| E[Alerta RETRASO_CRITICO +<br/>CASO automático +<br/>plantilla RETRASO_CRITICO]
    R --> F[Pedidos activos sin actualizar<br/>> N días]
    F --> G[Plantilla ACTUALIZACION_PERIODICA]
    D & E & G & M1 --> H[(comunicacion PENDING)]
    H --> I[Outbox 60 s → envío real]
```

**Regla de negocio clave:** un hito solo pasa a `COMPLETADO` con fecha
real; la notificación oportuna (≤2 h) alimenta el KPI
`FREQ_ACTUALIZACION_CLIENTE`.

---

## 3. Mensaje entrante del cliente (agente)

```mermaid
flowchart TD
    C[Cliente envía mensaje<br/>WhatsApp] --> W[POST /webhooks/whatsapp<br/>verifica firma]
    W --> I[(Registra comunicacion<br/>ENTRANTE / CLIENTE)]
    I --> CL{LLM clasifica:<br/>intención + sentimiento<br/>+ confianza}
    CL -->|ESTADO_PEDIDO / RETRASO| R1[Respuesta con plantilla<br/>de estado del pedido]
    CL -->|SALUDO| R2[Plantilla AGENTE_SALUDO]
    CL -->|CONSULTA_GENERAL| R3[Respuesta informativa]
    CL -->|PAGOS| R4[Redirige a asesor humano<br/>AGENTE_PAGOS_REDIRECT]
    CL -->|RECLAMO / DAÑO /<br/>PRODUCTO_INCORRECTO| E1[Escala: crea CASO +<br/>plantilla ESCALAMIENTO_CLIENTE]
    CL -->|confianza baja /<br/>multimedia| E2[Escala a caso humano]
    E1 & E2 & R1 & R2 & R3 & R4 --> O[Outbox → respuesta al cliente]
```

**Punto de no retorno:** cualquier mensaje de reclamo, daño o producto
incorrecto **nunca** se resuelve solo — siempre termina en un caso con
un humano responsable.

---

## 4. Entrega completa con conformidad

```mermaid
flowchart TD
    A[Todos los ítems del pedido<br/>LISTO_PARA_ENTREGA] --> B[Regla ENTREGA_LISTA:<br/>EN_COORDINACION + aviso]
    B --> C[Operador crea entrega COMPLETA<br/>POST /entregas]
    C --> D[estado EN_RUTA]
    D --> E[Llegada al destino]
    E --> F{Checklist por ítem:<br/>caja, modelo, color,<br/>capacidad, IMEI, accesorios}
    F -->|todo OK| G[resultado CONFORME<br/>ítem ENTREGADO]
    F -->|detalle encontrado| H[resultado CON_OBSERVACIONES<br/>+ observación + evidencia]
    G --> I{¿Todos los ítems<br/>entregados?}
    H --> I
    I -->|Sí| J[pedido CERRADO<br/>o CERRADO_CON_OBSERVACIONES]
    I -->|No| K[pedido sigue EN_COORDINACION]
    G & H & J --> M[Mensaje de confirmación<br/>al cliente vía outbox]
```

---

## 5. Entrega parcial autorizada

```mermaid
flowchart TD
    A[Cliente necesita parte del<br/>pedido antes de tiempo] --> B{¿Quién autoriza?}
    B -->|ADMIN| C[Registra parcial:<br/>autorizada_por + fecha + motivo]
    B -->|Sin autorización| X[(RECHAZADO:<br/>CHECK en BD y en servicio)]
    C --> D[POST /entregas tipo=PARCIAL<br/>solo los ítems listos]
    D --> E[Checklist solo de esos ítems]
    E --> F[ítems → ENTREGADO / CON_OBSERVACIONES]
    F --> G[pedido queda EN_PROCESO<br/>con el resto pendiente]
    G --> H[Seguimiento normal de los<br/>hitos restantes]
    H --> I[Cuando el resto esté listo:<br/>segunda entrega COMPLETA]
    I --> J[pedido CERRADO]
```

**Regla inviolable:** una entrega parcial exige **quién** la autorizó,
**cuándo** y **por qué** — validado dos veces (servicio + `CHECK` en BD).

---

## 6. Escalamiento de caso

```mermaid
flowchart TD
    A{Disparador} -->|Reclamo o tono negativo| B[caso RECLAMO]
    A -->|Atraso crítico| C[caso RETRASO_CRITICO<br/>creado por regla]
    A -->|Imprevisto abierto| D[caso IMPREVISTO]
    A -->|Falta de respuesta| E[caso FALTA_RESPUESTA]
    B & C & D & E --> F[(caso ABIERTO<br/>fecha_apertura)]
    F --> G[Humano atiende:<br/>POST /casos/{id} con<br/>fecha_primera_accion]
    G --> H[estado EN_PROCESO<br/>responsable asignado]
    H --> I{¿Resuelto?}
    I -->|Sí| J[estado RESUELTO<br/>fecha_cierre + descripción]
    I -->|No| K[Sigue en cola<br/>KPI: tiempo de respuesta]
    J --> L[Caso cerrado<br/>→ alimenta fact_escalamiento]
```

**KPI asociado:** `TIEMPO_RESPUESTA_ESCALADOS` = horas promedio entre
`fecha_apertura` y `fecha_primera_accion` (solo casos con acción).

---

## 7. Imprevisto (incidencia)

```mermaid
flowchart TD
    A[Se detecta la incidencia<br/>aduanera / operativa / proveedor] --> B[POST /imprevistos<br/>fecha_deteccion + tipo + descripción]
    B --> C[(imprevisto ABIERTO)]
    C --> D[Regla imprevisto:<br/>Alerta IMPREVISTO +<br/>CASO automático]
    D --> E[Responsable investiga<br/>estado EN_PROCESO]
    E --> F{¿Resuelto?}
    F -->|Sí| G[fecha_resolucion + resolución<br/>obligatorias → RESUELTO]
    F -->|No| E
    G --> H[Alerta atendida<br/>caso cerrado]
    H --> I[fact_sync →<br/>KPI TIEMPO_RESOLUCION_IMPREVISTOS<br/>(días promedio por tipo)]
```

---

## 8. Comunicación saliente y actualización de KPIs

```mermaid
flowchart TD
    subgraph Origen
        A[Regla / Agente / Operador]
    end
    A -->|misma transacción| B[(comunicacion<br/>estado_entrega = PENDING)]
    B --> C{Outbox cada 60 s}
    C -->|canal WHATSAPP| D[WhatsApp Cloud API<br/>o dry-run local]
    C -->|canal EMAIL| E[Email o mock]
    D & E --> F{¿Éxito?}
    F -->|Sí| G[SENT + wamid + enviado_en]
    F -->|No| H[intentos + 1<br/>proximo_intento = backoff]
    H -->|reintentos &lt; máximo| C
    H -->|reintentos agotados| I[FAILED +<br/>fallback email si está activo]
    G & I --> J[(auditoría completa en BD)]
    J --> K[fact_sync cada 5 min:<br/>fact_* ← tablas operacionales]
    K --> L[KPIs y series<br/>GET /dashboard/resumen<br/>GET /kpis/{codigo}/serie]
    L --> M[Dashboard con semáforos<br/>y filtros producto/origen/operador]
```

**Dos invariantes de este flujo:**
1. **Nada se envía sin haberse registrado primero** (outbox transaccional).
2. **Los KPIs solo leen `fact_*`** — nunca las tablas en caliente
   (estabilidad de las consultas del dashboard).

---

**Anterior:** [`04-agente.md`](04-agente.md) ·
**Siguiente:** [`05-manual-usuario.md`](05-manual-usuario.md)

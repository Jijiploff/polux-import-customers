# 📦 Modelo de flujo y ventanas — Módulo Entregas con IA

Diseño completo del flujo conversacional con IA y de las pantallas del sistema. **No es código**, es la especificación UX/UI lista para implementar.

---

## 1. Principios de diseño (los 8 mandamientos del nuevo flujo)

| # | Principio | Por qué |
|---|---|---|
| 1 | **La IA agrupa, no bombardea** | Máx. 2-3 mensajes por turno. Nunca un mensaje por campo. |
| 2 | **La IA muestra resumen antes de crear** | El cliente ve todos los datos juntos y confirma una sola vez. |
| 3 | **El cliente confirma, no la IA** | La IA prepara, el cliente autoriza con un botón. |
| 4 | **La IA no edita datos ya confirmados** | Si el cliente se equivoca → se escala a operador. |
| 5 | **El operador edita desde el sistema** | Auditoría centralizada, no en el chat. |
| 6 | **Un borrador puede convivir con la edición del operador** | No se destruye el trabajo previo. |
| 7 | **Toda la conversación se persiste** | Trazabilidad Ley 29733 + auditoría interna. |
| 8 | **Los estados son visibles en todo momento** | El cliente sabe si es BORRADOR, PROGRAMADA o ENTREGADA. |

---

## 2. Flujo general (ciclo completo)

```
┌──────────────────────────────────────────────────────────────────────┐
│                    FLUJO DE ENTREGA CON IA + OPERADOR                │
└──────────────────────────────────────────────────────────────────────┘

    ┌─────────────┐
    │   CLIENTE   │
    └──────┬──────┘
           │ "Quiero coordinar la entrega"
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  FASE 1 — RECOLECCIÓN (la IA agrupa 3 turnos)                │
    │                                                              │
    │  Turno 1 → Pregunta modalidad + dirección (o punto recojo)   │
    │  Turno 2 → Pregunta receptor + ventana horaria               │
    │  Turno 3 → Pregunta notas finales (opcional, se puede saltar)│
    └──────┬───────────────────────────────────────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  FASE 2 — RESUMEN + CONFIRMACIÓN                             │
    │                                                              │
    │  IA envía un solo mensaje con TODOS los datos en tarjeta     │
    │  + 2 botones:  [ ✅ Confirmar ]  [ ✏️ Corregir ]              │
    └──────┬───────────────────────────────────────────────────────┘
           │
           ├──── Cliente toca "Corregir" ────┐
           │                                 ▼
           │                    Vuelve a Fase 1 (solo el campo
           │                    que quiere corregir, sin reempezar)
           │
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  FASE 3 — CLIENTE CONFIRMA → IA CREA ENTREGA (PROGRAMADA)    │
    │                                                              │
    │  - Se crea la entrega en estado PROGRAMADA                   │
    │  - Se registra `creado_por_agente=true`                      │
    │  - Se registra `confirmada_por_id=null` (cliente confirmó,    │
    │    pero el operador AÚN NO valida)                           │
    │  - Se notifica al operador por Telegram con resumen          │
    └──────┬───────────────────────────────────────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  FASE 4 — OPERADOR REVISA Y CONFIRMA (PROGRAMADA → VALIDADA) │
    │                                                              │
    │  - Operador abre /entregas y ve la entrega con badge         │
    │    "📝 Creada por IA — pendiente de revisión"                │
    │  - Puede: Editar / Confirmar / Rechazar (crear otra)         │
    │  - Al confirmar: `confirmada_por_id=operador`                │
    └──────┬───────────────────────────────────────────────────────┘
           │
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  FASE 5 — ENTREGA FÍSICA (operador completa con conformidad) │
    └──────┬───────────────────────────────────────────────────────┘
           │
           ▼
    ┌──────────────┐
    │   ENTREGADA  │  (inmutable)
    └──────────────┘


    ─────────────────────────────────────────────────────────────────
    RAMA DE ERROR: cliente se equivocó después de confirmar
    ─────────────────────────────────────────────────────────────────

    Cliente: "Me equivoqué, la dirección era otra"
           │
           ▼
    ┌──────────────────────────────────────────────────────────────┐
    │  IA NO EDITA. Responde:                                      │
    │  "Entiendo. Como ya confirmaste la entrega, para modificarla │
    │   necesito que un asesor lo haga desde el sistema. Lo he     │
    │   escalado con prioridad alta. Te contactará en menos de     │
    │   2 horas hábiles."                                          │
    │                                                              │
    │  → Crea CasoEscalamiento motivo=MODIFICAR_ENTREGA (nuevo)    │
    │  → Notifica al operador por Telegram con los datos actuales  │
    │  → El operador edita la entrega desde /entregas/{id}         │
    └──────────────────────────────────────────────────────────────┘
```

---

## 3. Flujo conversacional detallado de la IA

### 3.1. Diagrama de turnos

```
┌─────────────────────────────────────────────────────────────────────┐
│ CLIENTE                      │  IA                                 │
├──────────────────────────────┼──────────────────────────────────────┤
│                              │                                      │
│ "Quiero coordinar la entrega"│                                      │
│ ────────────────────────────►│                                      │
│                              │ 📦 Vamos a coordinar tu entrega,     │
│                              │    Jorge. Necesito 3 datos:          │
│                              │                                      │
│                              │    1️⃣ ¿Delivery o recojo?            │
│                              │    2️⃣ Dirección / punto de recojo    │
│                              │    3️⃣ Quién recibe y cuándo          │
│                              │                                      │
│                              │ Empecemos por el 1️⃣:                 │
│                              │ ¿Prefieres delivery a domicilio      │
│                              │ (costo según zona) o recojo          │
│                              │ coordinado (sin costo)?              │
│                              │                                      │
│                              │ [🏠 Delivery]  [🤝 Recojo]            │
│                              │                                      │
│ "Delivery"                   │                                      │
│ ────────────────────────────►│                                      │
│                              │ Perfecto. Ahora envíame la dirección │
│                              │ completa en un solo mensaje, con     │
│                              │ este formato:                        │
│                              │                                      │
│                              │ 📍 Dirección, número, dpto           │
│                              │ 🏙️ Distrito                          │
│                              │ 🧭 Referencia (opcional)             │
│                              │                                      │
│                              │ Ejemplo:                             │
│                              │ Av. Larco 123, Dpto 501              │
│                              │ Trujillo                             │
│                              │ Frente al parque                     │
│                              │                                      │
│ "Av. España 456, Dpto 302    │                                      │
│  Trujillo                    │                                      │
│  Cerca al óvalo"             │                                      │
│ ────────────────────────────►│                                      │
│                              │ ✅ Dirección recibida.               │
│                              │                                      │
│                              │ Ahora, ¿quién recibe y cuándo?       │
│                              │ Envíame también en un solo mensaje:  │
│                              │                                      │
│                              │ 👤 Nombre completo del receptor      │
│                              │ 🪪 DNI                               │
│                              │ 📱 Teléfono de contacto              │
│                              │ 📅 Día preferido (AAAA-MM-DD)        │
│                              │ 🕐 Franja horaria (ej: 15:00-18:00)  │
│                              │                                      │
│                              │ Ejemplo:                             │
│                              │ Jorge Quispe                         │
│                              │ 70000004                             │
│                              │ 987654321                            │
│                              │ 2026-11-20                           │
│                              │ 15:00-18:00                          │
│                              │                                      │
│ "Jorge Quispe                │                                      │
│  70000004                    │                                      │
│  987654321                   │                                      │
│  2026-11-20                  │                                      │
│  15:00-18:00"                │                                      │
│ ────────────────────────────►│                                      │
│                              │ ⚠️ Falta la referencia de tu          │
│                              │    dirección (opcional, escríbela    │
│                              │    o envía /saltar).                 │
│                              │                                      │
│ "/saltar"                    │                                      │
│ ────────────────────────────►│                                      │
│                              │ ✅ Perfecto. Revisa el resumen:      │
│                              │                                      │
│                              │ ┌──────────────────────────────────┐ │
│                              │ │  📦 RESUMEN DE ENTREGA           │ │
│                              │ ├──────────────────────────────────┤ │
│                              │ │ Pedido: PD-2025-0005             │ │
│                              │ │ Tipo:   Completa                 │ │
│                              │ │                                  │ │
│                              │ │ 🚚 Modalidad: Delivery           │ │
│                              │ │ 📍 Dirección:                    │ │
│                              │ │    Av. España 456, Dpto 302      │ │
│                              │ │    Trujillo                      │ │
│                              │ │                                  │ │
│                              │ │ 👤 Receptor:                     │ │
│                              │ │    Jorge Quispe                  │ │
│                              │ │    DNI 70000004                  │ │
│                              │ │    Tel 987654321                 │ │
│                              │ │                                  │ │
│                              │ │ 📅 Fecha: 20/11/2026             │ │
│                              │ │ 🕐 Horario: 15:00 - 18:00        │ │
│                              │ └──────────────────────────────────┘ │
│                              │                                      │
│                              │ ¿Todo correcto?                      │
│                              │                                      │
│                              │ [ ✅ Confirmar ]  [ ✏️ Corregir ]     │
│                              │                                      │
│ "✅ Confirmar"               │                                      │
│ ────────────────────────────►│                                      │
│                              │ 🎉 ¡Listo, Jorge!                    │
│                              │                                      │
│                              │ Tu entrega fue registrada:           │
│                              │ • Pedido PD-2025-0005                │
│                              │ • Delivery a Av. España 456          │
│                              │ • 20/11/2026 entre 15:00 y 18:00     │
│                              │                                      │
│                              │ Un asesor la revisará en las         │
│                              │ próximas 2 horas hábiles y te        │
│                              │ confirmará la fecha exacta.          │
│                              │                                      │
│                              │ ¿Algo más?                           │
│                              │                                      │
└──────────────────────────────┴──────────────────────────────────────┘
```

### 3.2. Ejemplo del caso "cliente se equivoca"

```
┌─────────────────────────────────────────────────────────────────────┐
│ CLIENTE                      │  IA                                 │
├──────────────────────────────┼──────────────────────────────────────┤
│                              │                                      │
│ "Me equivoqué, la dirección  │                                      │
│  era otra"                   │                                      │
│ ────────────────────────────►│                                      │
│                              │ Entiendo, Jorge. Como ya confirmaste │
│                              │ la entrega, yo no puedo modificarla  │
│                              │ desde aquí.                          │
│                              │                                      │
│                              │ Voy a escalarlo con un asesor para   │
│                              │ que la edite desde el sistema. Te    │
│                              │ contactará en menos de 2 horas       │
│                              │ hábiles.                             │
│                              │                                      │
│                              │ Si quieres adelantar, envíame la     │
│                              │ dirección correcta y la adjunto al   │
│                              │ caso (el asesor la usará al editar): │
│                              │                                      │
│ "Av. Larco 789, San Isidro"  │                                      │
│ ────────────────────────────►│                                      │
│                              │ ✅ Anotado. El asesor recibirá tu    │
│                              │ mensaje junto con el caso.           │
│                              │                                      │
│                              │ Mientras tanto, si necesitas algo    │
│                              │ más, aquí estoy.                     │
│                              │                                      │
└──────────────────────────────┴──────────────────────────────────────┘

    (En paralelo, el operador recibe en Telegram:)

    ┌────────────────────────────────────────────────────────────┐
    │  🚨 Caso #N · MODIFICAR_ENTREGA                            │
    │  Pedido: PD-2025-0005                                       │
    │  Prioridad: ALTA                                            │
    │  Cliente: Jorge Quispe                                      │
    │  Motivo: Cliente se equivocó en los datos de la entrega    │
    │                                                            │
    │  Entrega actual #7 (PROGRAMADA por IA):                    │
    │  • Dirección: Av. España 456, Dpto 302                     │
    │                                                            │
    │  Cliente indica corrección:                                │
    │  "Av. Larco 789, San Isidro"                               │
    │                                                            │
    │  [ 📄 Ver entrega ]  [ ✏️ Editar entrega ]                  │
    │  [ ✅ Cerrar caso ]                                         │
    └────────────────────────────────────────────────────────────┘
```

### 3.3. Reglas de agrupación de datos

| Turno | Qué pide | Por qué agrupado |
|---|---|---|
| **Turno 1** | Modalidad + (dirección completa o punto de recojo) | Es una decisión + su dato dependiente |
| **Turno 2** | Receptor (nombre, DNI, tel) + ventana horaria (día, franja) | Son datos del "evento entrega" |
| **Turno 3** | Referencia y notas (opcional, se puede saltar con `/saltar`) | Datos finos que no todos tienen |
| **Turno 4** | Resumen + botones de confirmación | El cliente valida todo junto |

**Nunca** pide más de **2 grupos** de datos por mensaje. Si el cliente responde mal o incompleto, la IA repite solo **el grupo faltante**, no todo.

---

## 4. Ventanas del sistema

### 4.1. Ventana A — Lista de entregas (`/entregas`)

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ENTREGAS                                                       [+ Nueva]│
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Filtrar por pedido: [PD-2025-0005 ▼]   Estado: [Todos ▼]   [🔍]         │
│                                                                          │
├──────┬────────┬──────────┬──────────┬──────────┬─────────────────┬──────┤
│  #   │ Pedido │ Tipo     │ Modalidad│ Estado   │ Programada      │ Acc. │
├──────┼────────┼──────────┼──────────┼──────────┼─────────────────┼──────┤
│  7   │ 0005   │ Completa │ Delivery │ 📝 BORRADOR│ 20/11 15-18h  │ ⋮    │
│      │        │          │          │ (IA)     │                 │      │
├──────┼────────┼──────────┼──────────┼──────────┼─────────────────┼──────┤
│  6   │ 0003   │ Parcial  │ Recojo   │ ✅ PROGRAMADA│ 18/11 10-13h │ ⋮    │
│      │        │          │          │ (revisada)│                │      │
├──────┼────────┼──────────┼──────────┼──────────┼─────────────────┼──────┤
│  5   │ 0001   │ Completa │ Delivery │ 🚚 EN_RUTA│ 15/11 09-12h  │ ⋮    │
├──────┼────────┼──────────┼──────────┼──────────┼─────────────────┼──────┤
│  4   │ 0001   │ Parcial  │ Recojo   │ ✔ ENTREGADA│ 10/11 15h    │ ⋮    │
└──────┴────────┴──────────┴──────────┴──────────┴─────────────────┴──────┘
```

**Badges de estado:**

| Badge | Significado | Color |
|---|---|---|
| 📝 BORRADOR (IA) | La IA la creó, el operador aún no la valida | 🟡 Amarillo |
| 📝 BORRADOR | Creado manual, aún sin confirmar | 🟡 Amarillo |
| ✅ PROGRAMADA (revisada) | Confirmada por operador | 🟢 Verde claro |
| 🚚 EN_RUTA | El courier ya salió | 🔵 Azul |
| ✔ ENTREGADA | Completada con conformidad | 🟢 Verde fuerte |
| ❌ FALLIDA | No se pudo entregar | 🔴 Rojo |
| 🔄 REPROGRAMADA | Reprogramada | 🟠 Naranja |

**Menú de acciones (⋮) por fila:**

- Si **BORRADOR**: `Ver` `Editar` `Confirmar` `Rechazar`
- Si **PROGRAMADA**: `Ver` `Editar` `Completar`
- Si **EN_RUTA**: `Ver` `Editar (contacto)` `Completar`
- Si **ENTREGADA**: `Ver` (solo lectura)

---

### 4.2. Ventana B — Formulario Crear / Editar entrega

Se abre al hacer click en `+ Nueva` o en `Editar` de una fila.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Programar entrega · PD-2025-0005                                   [X] │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─ PASO 1 de 2 ─────────────────────────────────────────────────────┐  │
│  │ Tipo de entrega *           Modalidad *                           │  │
│  │ ◉ Completa (todos los ítems)  ◉ Delivery                          │  │
│  │ ○ Parcial (excepción)          ○ Recojo coordinado                │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ Si DELIVERY ─────────────────────────────────────────────────────┐  │
│  │                                                                    │  │
│  │  Dirección completa *                                            │  │
│  │  ┌──────────────────────────────────────────────────────────────┐│  │
│  │  │ Av. España 456, Dpto 302                                     ││  │
│  │  └──────────────────────────────────────────────────────────────┘│  │
│  │                                                                    │  │
│  │  Distrito *                  Referencia                           │  │
│  │  ┌──────────────────┐        ┌──────────────────────────────────┐│  │
│  │  │ Trujillo         │        │ Cerca al óvalo                   ││  │
│  │  └──────────────────┘        └──────────────────────────────────┘│  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ Si RECOJO ───────────────────────────────────────────────────────┐  │
│  │  Punto de recojo *                                                │  │
│  │  ┌──────────────────────────────────────────────────────────────┐│  │
│  │  │ Mall Aventura - Food Court                                   ││  │
│  │  └──────────────────────────────────────────────────────────────┘│  │
│  │  Referencia                                                       │  │
│  │  ┌──────────────────────────────────────────────────────────────┐│  │
│  │  │ Frente a Starbucks                                           ││  │
│  │  └──────────────────────────────────────────────────────────────┘│  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ PASO 2 de 2 ─ Datos del receptor + ventana horaria ──────────────┐  │
│  │                                                                    │  │
│  │  Nombre completo *          DNI *                                  │  │
│  │  ┌────────────────────────┐ ┌──────────────────────────────────┐  │  │
│  │  │ Jorge Quispe          │ │ 70000004                         │  │  │
│  │  └────────────────────────┘ └──────────────────────────────────┘  │  │
│  │                                                                    │  │
│  │  Teléfono de contacto *                                           │  │
│  │  ┌──────────────────────────────────────────────────────────────┐│  │
│  │  │ 987654321                                                    ││  │
│  │  └──────────────────────────────────────────────────────────────┘│  │
│  │                                                                    │  │
│  │  Día de entrega *           Franja horaria *                      │  │
│  │  ┌──────────────────┐        ┌──────────────────────────────────┐│  │
│  │  │ 2026-11-20       │        │ 15:00 - 18:00                    ││  │
│  │  └──────────────────┘        └──────────────────────────────────┘│  │
│  │                                                                    │  │
│  │  Notas para el courier (opcional)                                 │  │
│  │  ┌──────────────────────────────────────────────────────────────┐│  │
│  │  │ Portón negro, timbre 2. Llamar al llegar.                    ││  │
│  │  └──────────────────────────────────────────────────────────────┘│  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ Si PARCIAL: bloque adicional obligatorio ────────────────────────┐  │
│  │  Motivo de la entrega parcial *                                   │  │
│  │  ┌──────────────────────────────────────────────────────────────┐│  │
│  │  │ Cliente solicita separar por demora en aduana del iPhone     ││  │
│  │  └──────────────────────────────────────────────────────────────┘│  │
│  │                                                                    │  │
│  │  Ítems a entregar *                                               │  │
│  │  ☑ AirPods Pro 2 (LISTO_PARA_ENTREGA)                             │  │
│  │  ☐ iPhone 15 (EN_PROCESO) — deshabilitado                         │  │
│  │                                                                    │  │
│  │  ☑ Confirmo autorización humana registrada                        │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌─ Previsualización (opcional, para el operador) ───────────────────┐  │
│  │  Este es el mensaje que verá el cliente:                          │  │
│  │  "Hola Jorge, tu entrega fue coordinada:                          │  │
│  │   Delivery a Av. España 456, Trujillo                              │  │
│  │   El 20/11/2026 entre 15:00 y 18:00                               │  │
│  │   Recibe: Jorge Quispe (DNI 70000004)"                            │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  [ Cancelar ]                       [ Guardar como BORRADOR ]  [Programar]│
└──────────────────────────────────────────────────────────────────────────┘
```

**Diferencias entre "Guardar como BORRADOR" y "Programar":**

| Botón | Estado resultante | ¿Notifica al cliente? | ¿Cuándo usar? |
|---|---|---|---|
| Guardar como BORRADOR | `BORRADOR` | ❌ No | Cuando se quiere preparar y confirmar después |
| Programar | `PROGRAMADA` | ✅ Sí (opcional) | Cuando ya se validó todo |

---

### 4.3. Ventana C — Detalle de entrega (timeline)

Se abre al hacer click en una fila o en `Ver`.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Entrega #7 · PD-2025-0005                                         [X]  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─ Estado actual ───────────────────────────────────────────────────┐   │
│  │  📝 BORRADOR creado por IA                                        │   │
│  │  Pendiente de revisión por operador                               │   │
│  │                                                                    │   │
│  │  Creada: 12/11/2026 10:30 · Cliente confirmó por Telegram         │   │
│  │  Aún no validada por operador                                     │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─ Datos de la entrega ─────────────────────────────────────────────┐   │
│  │  Tipo:      Completa                                              │   │
│  │  Modalidad: Delivery                                              │   │
│  │                                                                    │   │
│  │  📍 Dirección: Av. España 456, Dpto 302                           │   │
│  │     Distrito: Trujillo                                            │   │
│  │     Referencia: Cerca al óvalo                                    │   │
│  │                                                                    │   │
│  │  👤 Receptor: Jorge Quispe (DNI 70000004)                         │   │
│  │     Teléfono: 987654321                                           │   │
│  │                                                                    │   │
│  │  📅 Fecha: 20/11/2026                                             │   │
│  │  🕐 Franja: 15:00 - 18:00                                         │   │
│  │                                                                    │   │
│  │  Notas: Portón negro, timbre 2                                    │   │
│  │                                                                    │   │
│  │  Ítems incluidos:                                                 │   │
│  │    • iPhone 15 128GB Azul (1x)                                    │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─ Origen y auditoría ──────────────────────────────────────────────┐   │
│  │  Creado por: 🤖 IA (vía Telegram)                                 │   │
│  │  Cliente confirmó: ✅ Jorge Quispe · 12/11/2026 10:31             │   │
│  │  Operador validador: ⏳ Pendiente                                 │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─ Línea de tiempo ────────────────────────────────────────────────┐   │
│  │  12/11 10:28  🤖 IA inició coordinación por Telegram               │   │
│  │  12/11 10:30  🤖 IA recibió datos del cliente                     │   │
│  │  12/11 10:31  ✅ Cliente confirmó el resumen                      │   │
│  │  12/11 10:31  📝 Entrega creada (BORRADOR)                        │   │
│  │  12/11 10:31  📱 Operador notificado por Telegram                 │   │
│  │  ─────────── (pendiente: operador revisa) ───────────             │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  [ Cerrar ]   [ ✏️ Editar ]   [ ✅ Confirmar y programar ]                │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### 4.4. Ventana D — Modal de confirmación del operador

Se abre al hacer click en `✅ Confirmar y programar`.

```
┌──────────────────────────────────────────────────────────────────┐
│  ✅ Confirmar entrega #7                                    [X]  │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Al confirmar, se enviará el siguiente mensaje al cliente por    │
│  Telegram y la entrega pasará a estado PROGRAMADA.               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  📦 Hola Jorge, tu entrega fue confirmada:                 │  │
│  │                                                            │  │
│  │  🚚 Delivery a Av. España 456, Dpto 302                    │  │
│  │     Trujillo                                               │  │
│  │                                                            │  │
│  │  📅 20/11/2026 entre 15:00 y 18:00                         │  │
│  │                                                            │  │
│  │  👤 Recibe: Jorge Quispe (DNI 70000004)                    │  │
│  │                                                            │  │
│  │  Si hay algún cambio, avísame con anticipación.            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ☑ Enviar mensaje de confirmación al cliente                     │
│  ☐ Enviar recordatorio 24h antes de la entrega                   │
│                                                                  │
│  [ Cancelar ]                        [ ✅ Confirmar y programar ]│
└──────────────────────────────────────────────────────────────────┘
```

---

### 4.5. Ventana E — Notificación al operador en Telegram

Cuando la IA crea un borrador, el operador recibe este mensaje:

```
┌────────────────────────────────────────────────────────────┐
│  📝 BORRADOR DE ENTREGA #7                                 │
│  Pedido: PD-2025-0005                                      │
│                                                            │
│  El cliente Jorge Quispe confirmó estos datos por Telegram:│
│                                                            │
│  🚚 Delivery                                               │
│  📍 Av. España 456, Dpto 302 · Trujillo                    │
│  👤 Jorge Quispe · DNI 70000004 · Tel 987654321            │
│  📅 20/11/2026 · 15:00 - 18:00                             │
│                                                            │
│  ⚠️ Pendiente de tu validación. Revisa y confirma.          │
│                                                            │
│  [ 📄 Ver entrega ]  [ ✅ Confirmar ]  [ ✏️ Editar ]        │
└────────────────────────────────────────────────────────────┘
```

Y cuando el cliente se equivoca después de confirmar:

```
┌────────────────────────────────────────────────────────────┐
│  🚨 CASO #N · MODIFICAR_ENTREGA                            │
│  Pedido: PD-2025-0005                                      │
│  Prioridad: ALTA · SLA: 2h hábiles                         │
│                                                            │
│  Cliente Jorge Quispe reporta error en entrega #7          │
│                                                            │
│  Cambio solicitado:                                        │
│  "La dirección era Av. Larco 789, San Isidro, no Av.       │
│   España 456"                                              │
│                                                            │
│  Entrega actual:                                           │
│  📍 Av. España 456, Dpto 302 · Trujillo                    │
│  📅 20/11/2026 · 15:00 - 18:00                             │
│                                                            │
│  [ 📄 Ver entrega ]  [ ✏️ Editar entrega ]  [ ✅ Cerrar ]   │
└────────────────────────────────────────────────────────────┘
```

---

### 4.6. Ventana F — Modal de completar entrega (conformidad)

Ya existe (Fase 6), pero añado los **campos adicionales** que faltaban:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Completar entrega #7 · PD-2025-0005                                      │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Fecha real de entrega *                                                 │
│  [2026-11-20T16:30]                                                      │
│                                                                          │
│  ┌─ Datos del receptor (verificar al entregar) ─────────────────────┐   │
│  │  ☑ Confirmé identidad del receptor con DNI 70000004              │   │
│  │                                                                    │   │
│  │  ¿Quién recibió físicamente? *                                    │   │
│  │  ┌──────────────────────────────────────────────────────────────┐│   │
│  │  │ Jorge Quispe (mismo titular)                                 ││   │
│  │  └──────────────────────────────────────────────────────────────┘│   │
│  │                                                                    │   │
│  │  Si es distinto al titular:                                       │   │
│  │  ┌──────────────────────────────────────────────────────────────┐│   │
│  │  │ (nombre y DNI de quien recibe, con autorización)             ││   │
│  │  └──────────────────────────────────────────────────────────────┘│   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─ Conformidad por ítem ──────────────────────────────────────────┐   │
│  │  📱 iPhone 15 128GB Azul                                         │   │
│  │  ☑ Caja sellada    ☑ Modelo OK    ☑ Color OK                    │   │
│  │  ☑ Capacidad OK    ☑ IMEI OK      ☑ Accesorios OK               │   │
│  │  Resultado: [ Conforme ▼ ]                                       │   │
│  │  [Si CON_OBSERVACIONES] Observaciones *: [________]              │   │
│  │  Evidencias (URLs): [__________________]                         │   │
│  └────────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  [ Cancelar ]                            [ Registrar entrega completa ]  │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Máquina de estados completa

```
                     ┌────────────────┐
                     │    (creación)  │
                     └───────┬────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │  BORRADOR    │  │  PROGRAMADA  │  │  PROGRAMADA  │
    │  (IA)        │  │  (manual)    │  │  (agente)    │
    └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
           │                 │                 │
           │ ← cliente puede  │                 │
           │   corregir       │                 │
           │                 │                 ▼
           │                 │          Operador confirma
           │                 │                 │
           ▼                 ▼                 ▼
    ┌──────────────────────────────────────────────┐
    │  PROGRAMADA (validada por operador)          │
    └──────────────────┬───────────────────────────┘
                       │
                       │ (courier en ruta)
                       ▼
                ┌──────────────┐
                │   EN_RUTA    │
                └──────┬───────┘
                       │
           ┌───────────┼────────────┐
           │           │            │
           ▼           ▼            ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ENTREGADA │ │ FALLIDA  │ │REPROGRAM.│
    │(inmutable)│ │(inmutable)│ │(editable)│
    └──────────┘ └──────────┘ └────┬─────┘
                                    │
                                    └──→ PROGRAMADA
                                         (nueva fecha)
```

**Transiciones y quién puede hacerlas:**

| Desde | Hacia | Quién | Notifica |
|---|---|---|---|
| — | BORRADOR (IA) | IA (automático) | Operador |
| — | BORRADOR (manual) | Operador | — |
| BORRADOR (IA) | PROGRAMADA | Operador (confirmar) | Cliente |
| BORRADOR (manual) | PROGRAMADA | Operador (confirmar) | Cliente |
| PROGRAMADA | EN_RUTA | Operador o courier | Cliente |
| EN_RUTA | ENTREGADA | Operador (completar) | Cliente |
| EN_RUTA | FALLIDA | Operador | Cliente |
| FALLIDA | REPROGRAMADA | Operador | Cliente |
| REPROGRAMADA | PROGRAMADA | Operador | Cliente |
| PROGRAMADA | BORRADOR | ❌ No permitido | — |
| ENTREGADA | * | ❌ Inmutable | — |

---

## 6. Manejo de errores y casos borde

| Caso | Qué hace el sistema | Qué ve el cliente |
|---|---|---|
| Cliente responde mal un grupo | IA repite solo el grupo faltante con ejemplo | Pregunta puntual |
| Cliente escribe `/saltar` en campo opcional | Salta el campo | Continúa al siguiente |
| Cliente toca `✏️ Corregir` en el resumen | IA vuelve al grupo que quiere corregir | Pregunta específica |
| Cliente escribe datos después de confirmar | IA NO edita → escala a operador | "Un asesor lo editará" |
| Operador rechaza un borrador | Pasa a `RECHAZADA` (nuevo estado) | IA informa y ofrece rehacer |
| Cliente pregunta por el estado del borrador | IA dice "está pendiente de confirmación por asesor" | Mensaje claro |
| Operador no confirma en 24h | Motor de reglas envía alerta al operador | Cliente no se entera |
| Cliente cancela antes de confirmar | IA cierra el borrador (queda en BD como cancelado) | "Cancelado, avísame si quieres rehacerlo" |
| Datos incompatibles (ej. fecha pasada) | IA pide corregir el campo | "La fecha ya pasó, dime una nueva" |

---

## 7. Diferencias clave con el flujo anterior

| Aspecto | Flujo anterior | Flujo nuevo |
|---|---|---|
| Formulario de entrega | 3 campos | 12+ campos con validación por modalidad |
| Coordinación con IA | No existía | Guía conversacional en 3 turnos |
| Confirmación del cliente | No existía | Resumen + botones |
| Edición post-creación | Solo manual del operador | Manual del operador, IA deriva |
| Estado inicial | PROGRAMADA siempre | BORRADOR (IA) o PROGRAMADA (manual) |
| Operador revisa antes de programar | No | Sí (BORRADOR → PROGRAMADA) |
| Trazabilidad | `updated_by_id` | + `creado_por_agente`, `confirmada_por_id`, `fecha_confirmacion` |
| Notificación al operador | Solo por casos críticos | Siempre que la IA crea un borrador |
| Cliente puede corregir | No (no había flujo) | Sí, antes de confirmar; después → operador |

---

## 8. Resumen visual del ciclo completo

```
Cliente → IA (3 turnos) → Resumen → Confirma → BORRADOR
                                                    │
                                                    ▼
                                          Operador recibe aviso
                                                    │
                                                    ▼
                                          Revisa → Confirma
                                                    │
                                                    ▼
                                            PROGRAMADA
                                                    │
                                                    ▼
                                            Entrega física
                                                    │
                                                    ▼
                                          ENTREGADA (inmutable)

    ┌─────────────────────────────────────────────────────────┐
    │  En cualquier momento antes de ENTREGADA:               │
    │  Cliente pide cambio → IA escala a operador             │
    │  → Operador edita con formulario                        │
    │  → Se registra auditoría completa                       │
    └─────────────────────────────────────────────────────────┘
```

Con este modelo tienes:
- **UX clara**: el cliente no recibe 10 mensajes seguidos; recibe 3-4 bien agrupados.
- **Seguridad**: el operador siempre valida antes de programar.
- **Trazabilidad**: cada paso queda en `comunicacion` + `entrega` + caso si escala.
- **Flexibilidad**: se puede editar mientras no se haya entregado.
- **Regla inviolable intacta**: si es PARCIAL, sigue exigiendo autorización humana en el formulario.
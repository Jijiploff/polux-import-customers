# 🤖 Guía de integración del bot de Telegram — Polux Import

Guía paso a paso para activar el canal de Telegram en el sistema de
seguimiento al cliente, con derivación a empleados.

> **Estado previo requerido**: sistema levantado con Fases 0-8 completas
> (ver `LEVANTAMIENTO.md`). Migraciones aplicadas hasta `0009_caso_telegram_reply`.

---

## 📋 Tabla de contenido

1. [Requisitos previos](#1-requisitos-previos)
2. [Crear el bot en BotFather](#2-crear-el-bot-en-botfather)
3. [Configurar variables de entorno](#3-configurar-variables-de-entorno)
4. [Reconstruir backend y aplicar migración](#4-reconstruir-backend-y-aplicar-migración)
5. [Iniciar el bot (polling o webhook)](#5-iniciar-el-bot-polling-o-webhook)
6. [Vincular operadores (notificaciones y respuestas)](#6-vincular-operadores-notificaciones-y-respuestas)
7. [Probar el flujo completo](#7-probar-el-flujo-completo)
8. [Verificar en la base de datos](#8-verificar-en-la-base-de-datos)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Requisitos previos

Antes de empezar, confirma que el sistema base está operativo:

```cmd
:: Los 3 contenedores deben estar Up
docker compose ps

:: Backend responde
curl http://localhost:8000/api/v1/health

:: BD accesible
curl http://localhost:8000/api/v1/health/db

:: Migraciones al día (debe mostrar 0009_caso_telegram_reply como head)
docker compose exec -T backend alembic current
```

Si algo falla, primero resuelve el sistema base siguiendo `LEVANTAMIENTO.md`.

---

## 2. Crear el bot en BotFather

1. En Telegram, busca a **@BotFather** (verificado, con el check azul).
2. Envía el comando:
   ```
   /newbot
   ```
3. BotFather te pedirá:
   - **Nombre del bot**: por ejemplo `Polux Import Soporte`
   - **Username**: debe terminar en `_bot`, por ejemplo `polux_import_soporte_bot`
4. Si el username está libre, BotFather te dará un mensaje como:

   ```
   Done! Congratulations on your new bot...

   Use this token to access the HTTP API:
   123456789:ABCdef-GHIjklMNOpqrSTUvwxYZ12345678

   Keep your token secure and store it safely...
   ```

5. **Copia y guarda el token**. Lo necesitarás en el siguiente paso.

   > ⚠️ **Nunca** subas el token a GitHub. Va solo en `.env` (que está en
   > `.gitignore`).

---

## 3. Configurar variables de entorno

Abre `.env` en el editor:

```cmd
notepad .env
```

Añade **al final** las siguientes líneas:

```env
# --- Telegram ---
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=123456789:ABCdef-GHIjklMNOpqrSTUvwxYZ12345678
TELEGRAM_WEBHOOK_SECRET=un-secreto-largo-aleatorio-aqui
TELEGRAM_OPERATOR_CHAT_ID=
TELEGRAM_API_TIMEOUT_SECONDS=15
# mock para pruebas locales; ai para usar Gemini en cada consulta de cliente
TELEGRAM_MODE=ai
```

Cambia:
- `TELEGRAM_BOT_TOKEN` → el token real que te dio BotFather.
- `TELEGRAM_WEBHOOK_SECRET` → una cadena aleatoria larga. Genera una con:

  ```cmd
  powershell -Command "[System.Guid]::NewGuid().ToString() + [System.Guid]::NewGuid().ToString()"
  ```

  O simplemente inventa algo como `polux-tg-secret-2026-a8f3c9b1d4e7`.

Deja:
- `TELEGRAM_ENABLED=false` **por ahora** (se activa en el paso 4).
- `TELEGRAM_OPERATOR_CHAT_ID=` **vacío**: los operadores se vinculan con `/vincular` (paso 6).

`TELEGRAM_MODE=ai` activa clasificación y redacción con Gemini. Requiere
`LLM_API_KEY`, `LLM_BASE_URL` y `LLM_MODEL` configurados en la sección
**Agente IA**. Usa `mock` para pruebas locales sin llamadas externas.

Guarda con **Ctrl + S** y cierra.

---

## 4. Reconstruir backend y aplicar migración

```cmd
:: 1. Reconstruir el backend (recarga los modelos y módulos nuevos)
docker compose build backend

:: 2. Levantar el backend con el nuevo código
docker compose up -d backend

:: 3. Esperar a "Application startup complete"
docker compose logs --tail=20 backend
```

Debes ver en el log algo como:

```
{"asctime": "...", "levelname": "INFO", "name": "app.startup", "message": "startup", "env": "development", "version": "0.1.0"}
INFO:     Application startup complete.
```

**Ahora aplica las migraciones** `0007_telegram_channel` y `0008_usuario_telegram`:

```cmd
:: 4. Confirmar dónde estás
docker compose exec -T backend alembic current
:: → debe decir "0006_dimensional_kpi_views (head)"

:: 5. Aplicar la migración de Telegram
docker compose exec -T backend alembic upgrade head
```

Salida esperada:

```
INFO  [alembic.runtime.migration] Running upgrade 0006_dimensional_kpi_views -> 0007_telegram_channel
```

Verifica que todo se creó:

```cmd
:: Columna telegram_chat_id en cliente
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2026" -d PoluxImportDB -Q "SELECT name FROM sys.columns WHERE object_id = OBJECT_ID('cliente') AND name = 'telegram_chat_id';"

:: Fila TELEGRAM en dim_canal
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2026" -d PoluxImportDB -Q "SELECT codigo FROM dim_canal;"
```

Deben aparecer `telegram_chat_id` y `TELEGRAM` respectivamente.

**Activa el canal Telegram** en `.env`:

```env
TELEGRAM_ENABLED=true
```

Y reinicia:

```cmd
docker compose restart backend
```

---

## 5. Iniciar el bot (polling o webhook)

Elige **una** de las dos opciones. Para desarrollo local **recomiendo polling** porque no requiere ngrok ni URL pública.

### 🅰️ Opción A: Polling (recomendado para dev)

Abre **una segunda terminal** en la raíz del proyecto y ejecuta:

```cmd
docker compose exec backend python -m scripts.telegram_poll
```

Salida esperada:

```
{"levelname": "INFO", "name": "telegram_poll", "message": "webhook_removed_for_polling"}
{"levelname": "INFO", "name": "telegram_poll", "message": "telegram_polling_started"}
```

El bot ya está escuchando. **Déjalo corriendo** mientras pruebas.

En Docker Compose también puedes dejarlo permanente con:

```cmd
docker compose up -d telegram_poll
```

El servicio se reinicia automáticamente si el backend o el contenedor se
reinician. No ejecutes además un segundo polling manual al mismo tiempo.

> 💡 Este comando:
> - Elimina cualquier webhook previo.
> - Consulta mensajes cada 30 segundos.
> - Procesa los mensajes con el `AgentService` (tu agente IA).
> - Envía las respuestas por Telegram.
>
> Para detenerlo: **Ctrl + C** en esa terminal.

### 🅱️ Opción B: Webhook (si tienes ngrok o dominio público)

Abre una terminal y expón el backend:

```cmd
ngrok http 8000
```

Copia la URL HTTPS que te da ngrok (ej. `https://a1b2c3.ngrok-free.app`).

Configura el webhook:

```cmd
curl -X POST "https://api.telegram.org/bot<TU_TOKEN>/setWebhook" ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://a1b2c3.ngrok-free.app/api/v1/webhooks/telegram\",\"secret_token\":\"<TU_SECRET>\"}"
```

Reemplaza `<TU_TOKEN>` con el token del paso 2 y `<TU_SECRET>` con el
`TELEGRAM_WEBHOOK_SECRET` del paso 3.

Verifica:

```cmd
curl "https://api.telegram.org/bot<TU_TOKEN>/getWebhookInfo"
```

Debe mostrar `"url":"https://a1b2c3.ngrok-free.app/api/v1/webhooks/telegram"`.

> ⚠️ Con webhook **no** corras el polling al mismo tiempo. Son mutuamente
> excluyentes (polling elimina el webhook).

---

## 6. Vincular operadores (notificaciones y respuestas)

Pueden ser **varios operadores**. Cada uno vincula su propio chat con sus
credenciales de Polux Import; no se comparte una contraseña.

1. El operador abre el bot y envía:
   ```
   /vincular operador@poluximport.pe SuContraseña
   ```
2. El bot valida:
   - email y contraseña contra `usuario.password_hash` (bcrypt),
   - que el usuario esté `activo`,
   - que tenga rol `ADMIN`, `OPERADOR` o `GERENTE`.
3. Si todo es correcto, responde:
   ```
   ✅ Vinculado como operador: Nombre Apellido. Recibirás las notificaciones de casos.
   ```
4. Repite el paso 1 con cada operador. **Todos** los operadores vinculados y
   activos reciben las notificaciones de casos.
5. Para dejar de recibirlas, el operador envía:
   ```
   /desvincular
   ```

> 🔒 La contraseña **no se guarda** en la base de datos ni en el historial de
> `comunicacion`; sólo se usa para verificar el hash. Aun así, se recomienda
> borrar el mensaje de Telegram después de vincular.
>
> 🔒 Tras 5 intentos fallidos desde un mismo chat, el bot bloquea nuevos
> intentos durante 15 minutos.
>
> ⚙️ `TELEGRAM_OPERATOR_CHAT_ID` queda como **destinatario de respaldo**
> opcional (por ejemplo, el chat del administrador). Los operadores vinculados
> por `/vincular` reciben las notificaciones sin tocar `.env`.

---

## 7. Probar el flujo completo

Con el bot corriendo (polling en una terminal), ejecuta las siguientes pruebas.

### Test 1 — Vinculación del cliente

1. En Telegram, abre tu bot y envía:
   ```
   /start
   ```
2. El bot responde:
   ```
   👋 Bienvenido a Polux Import.

   Para consultar el estado de tu pedido, envíame tu código junto con tu DNI
   (por ejemplo: PD-2025-0001 70000001).

   Si necesitas hablar con un asesor, escribe tu consulta y te derivaré.
   ```
3. Envía sólo el código de un pedido existente:
   ```
   PD-2025-0001
   ```
4. El bot pide el DNI (no vincula todavía):
   ```
   Para vincular tu pedido necesito validar tu identidad.
   Envíame el código del pedido junto con tu DNI en un solo mensaje.
   Ejemplo: PD-2025-0001 70000001
   ```
5. Envía código + DNI del titular del pedido:
   ```
   PD-2025-0001 70000001
   ```
6. El bot responde:
   ```
   ✅ Vinculado al pedido PD-2025-0001. Ya puedes consultar su estado.
   ```

> **Seguridad**: si el DNI no coincide con el `documento` del cliente, el bot
> responde con un mensaje genérico y no vincula. Si el pedido ya está vinculado
> a otro chat, tampoco permite reemplazarlo.

### Test 2 — Consulta de estado

1. Envía:
   ```
   ¿Cómo va mi pedido?
   ```
2. El bot responde con el estado real del pedido (consultado de la BD):
   ```
   Hola María Rodríguez, tu pedido PD-2025-0001 está en proceso.
   Fecha prometida: 14/11/2026. Avance: AirPods Pro 2 — EN_PROCESO
   (próximo hito: Preparación el 08/11/2026).
   ```

### Test 3 — Escalamiento por reclamo

1. Envía:
   ```
   Esto es una estafa, quiero mi reembolso
   ```
2. El bot responde (mensaje de holding):
   ```
   Hola María Rodríguez, hemos derivado tu caso con un asesor
   que te contactará en breve.
   ```
3. **En tu otra cuenta de Telegram** (el operador configurado en el paso 6),
   recibirás una notificación con botones:
   ```
   🚨 Nuevo caso #N · RECLAMO
   Pedido: PD-2025-0001
   Prioridad: ALTA
   Cliente: María Rodríguez
   Descripción: Comunicación entrante detectada como RECLAMO. Escalar sin resolver.

   Pulsa un botón o responde citando este mensaje para atender el caso.

   [📄 Ver caso]  [💬 Responder]
   [✅ Cerrar caso]
   ```

### Test 4 — Entrega parcial (regla inviolable)

1. Envía:
   ```
   Quiero recibir solo los AirPods primero
   ```
2. El bot **no decide** — responde:
   ```
   Hola María Rodríguez, hemos derivado tu caso con un asesor
   que te contactará en breve.
   ```
3. El operador recibe:
   ```
   🚨 Nuevo caso #N · ENTREGA_PARCIAL
   Pedido: PD-2025-0001
   Prioridad: ALTA
   ...
   ```

### Test 5 — Daño

1. Envía:
   ```
   El iPhone llegó roto, la pantalla está quebrada
   ```
2. El operador recibe un caso con **prioridad CRÍTICA**.

### Test 6 — Ver el caso en el frontend

1. Abre `http://localhost:5173`
2. Login como `operador@poluximport.pe` / `Oper123!`
3. Ve a **Casos**
4. Verás los casos generados desde Telegram, con trazabilidad completa.

### Test 7 — Responder un caso desde Telegram

1. En el aviso del caso, pulsa **📄 Ver caso**: el bot muestra la ficha
   (estado, prioridad, responsable, pedido, fecha prometida, modalidad) y los
   últimos eventos de la línea de tiempo.
2. Pulsa **💬 Responder**. El bot confirma:
   ```
   💬 Caso #N activo. Escribe tu respuesta y la enviaré al cliente.
   Usa /salir para terminar.
   ```
3. Escribe la respuesta. El cliente la recibe en su chat de Telegram y el
   mensaje queda registrado como `HUMANO` / `TELEGRAM` en `comunicacion`.
4. Cuando el cliente vuelva a escribir, el bot **no responde solo**: reenvía
   el mensaje al operador responsable (o a todos si el caso aún no tiene
   responsable) con un botón para responder. Así la conversación sigue siendo
   un chat entre persona y persona.
5. También puedes responder **citando** el aviso del caso o el mensaje
   reenviado del cliente, o usar:
   ```
   /responder N Hola, ya estamos revisando tu caso.
   ```
6. El primer operador que responde queda como responsable. Si otro intenta
   responder, el bot le indica quién está atendiendo el caso. Un `ADMIN` sí
   puede responder casos ajenos y la asignación se mantiene.
7. Un operador puede soltar su caso con `/liberar N`; queda sin asignar para
   que otro lo tome. El historial y la primera acción se conservan.

> **Reglas de visibilidad:** `/casos` muestra al `ADMIN` todos los casos; al
> `OPERADOR`, solo los asignados a él y los libres. `/caso N` y los botones
> rechazan casos asignados a otro operador. El primer operador que responde
> un caso libre lo reclama.

> **Alternativa sin usar tu Telegram personal:** entra a la plataforma web
> como ADMIN/OPERADOR, abre **Contestador** (solo asignados) o
> **Casos → Responder** (asignados + libres) y escribe desde ahí. Usa el
> mismo `caso_service`: el primer operador queda asignado, la respuesta sale
> por Telegram y se registra igual. Si el cliente no vinculó su Telegram, la
> web responde `400 sin_telegram`, **no asigna el caso** y guarda el intento
> como `OPERATIVO` (auditoría). El hilo de la web muestra solo `CLIENTE`; los
> comandos y avisos internos quedan como `OPERATIVO`.

### Test 8 — Cerrar el caso desde Telegram

1. Pulsa **✅ Cerrar caso** (o envía `/cerrar N`).
2. El caso pasa a `CERRADO` con fecha de cierre.
3. El cliente recibe un aviso de cierre en su chat.
4. El operador sale automáticamente del modo respuesta.

### Comandos de operador

```
/casos                  → tus casos + los libres (ADMIN: todos)
/caso N                 → ficha + línea de tiempo
/responder N mensaje    → responder al cliente
/cerrar N               → cerrar el caso
/liberar N              → soltar tu caso para que otro lo tome
/salir                  → salir del modo respuesta
```

> El modo respuesta caduca a las 2 horas sin actividad. Usa `/salir` para
> terminarlo antes.
>
> WhatsApp queda desactivado (`WHATSAPP_ENABLED=false`): las respuestas
> humanas del bot y del panel web se entregan por Telegram.

---

## 8. Verificar en la base de datos

### Comunicaciones registradas

```cmd
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2026" -d PoluxImportDB -Q "SELECT TOP 10 id, canal, clase, direccion, intencion_detectada, estado_entrega, LEFT(contenido, 60) AS contenido FROM comunicacion ORDER BY id DESC;"
```

Debe mostrar comunicaciones con `canal=TELEGRAM`, alternando `ENTRANTE` (del
cliente) y `SALIENTE` (del agente), con `estado_entrega=SENT`. La columna
`clase` distingue `CLIENTE` (conversación) de `OPERATIVO` (comandos, avisos a
operadores y respuestas bloqueadas).

### Cliente vinculado

```cmd
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2026" -d PoluxImportDB -Q "SELECT nombre, telegram_chat_id FROM cliente WHERE telegram_chat_id IS NOT NULL;"
```

### Casos generados

```cmd
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2026" -d PoluxImportDB -Q "SELECT id, pedido_id, motivo, prioridad, estado FROM caso_escalamiento ORDER BY id DESC;"
```

---

## 9. Troubleshooting

### El bot no responde a los mensajes

| Causa | Solución |
|---|---|
| `TELEGRAM_ENABLED=false` | Cambiar a `true` en `.env` y reiniciar backend |
| `TELEGRAM_BOT_TOKEN` vacío o incorrecto | Verificar token copiado de BotFather |
| Polling no está corriendo | Ejecutar `docker compose exec backend python -m scripts.telegram_poll` |
| Webhook mal configurado | `curl ".../getWebhookInfo"` para verificar URL |
| Backend caído | `docker compose logs backend` |

### El bot responde "No encontré un pedido asociado"

- El cliente aún no envió un código de pedido válido.
- Verifica que el código exista: `SELECT codigo FROM pedido;`
- Enviar el código junto con el DNI del titular: `PD-2025-0001 70000001`.

### El bot responde "No pudimos validar el código y el DNI"

- El `documento` del cliente en la BD no coincide con el DNI enviado.
- Revisar: `SELECT codigo, c.documento FROM pedido p JOIN cliente c ON c.id = p.cliente_id;`
- Si el cliente no tiene `documento`, un operador debe completarlo antes de vincular.

### El operador no recibe notificaciones

| Causa | Solución |
|---|---|
| Ningún operador vinculado | Cada operador debe enviar `/vincular email contraseña` |
| Usuario sin rol `OPERADOR`/`ADMIN`/`GERENTE` | Asignar el rol en el panel web |
| Usuario inactivo | Activarlo antes de vincular |
| `TELEGRAM_OPERATOR_CHAT_ID` (fallback) mal copiado | Limpiar el valor en `.env` |
| Backend no reiniciado tras cambiar `.env` | `docker compose up -d --force-recreate backend` |
| El bot del operador no inició conversación | El operador debe enviar `/start` al bot primero |

### Error: `telegram_disabled`

Significa que `TELEGRAM_ENABLED=false` o `TELEGRAM_BOT_TOKEN` vacío. Revisar
`.env` y reiniciar.

### Error: `Conflict: terminated by other getUpdates request`

Dos procesos de polling corriendo a la vez. Detén todos menos uno:

```cmd
:: Buscar procesos python activos en el contenedor
docker compose exec backend ps aux | grep python
```

O simplemente reinicia el backend (mata el polling actual) y vuelve a lanzar
uno solo.

### Error: `webhook is active` al iniciar polling

El polling automáticamente elimina el webhook al arrancar. Si persiste:

```cmd
curl "https://api.telegram.org/bot<TU_TOKEN>/deleteWebhook"
```

Y vuelve a lanzar el polling.

### No quiero usar polling, prefiero webhook y no tengo ngrok

Instala **Cloudflare Tunnel** (gratis, sin cuenta):

```cmd
winget install --id Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8000
```

Te da una URL `https://xxx.trycloudflare.com` que puedes usar como webhook.

---

## 🎯 Resultado final

Después de completar esta guía tendrás:

- ✅ Bot de Telegram funcionando como canal de atención al cliente
- ✅ Vinculación automática cliente ↔ chat por código de pedido
- ✅ Consultas de estado con datos reales de la BD
- ✅ Escalamiento automático a operador (reclamos, daños, parciales, retrasos)
- ✅ Notificaciones en Telegram al operador cuando se abre un caso
- ✅ Trazabilidad completa en la tabla `comunicacion`
- ✅ Casos visibles en el frontend para su gestión

El bot se comporta **exactamente igual que la demo de WhatsApp**, pero usa
Telegram como transporte. Toda la lógica (agente IA, motor de reglas,
guardrails, regla inviolable de entrega parcial) se reutiliza sin duplicar.

---

## 📌 Comandos rápidos de referencia

```cmd
:: Iniciar bot (polling)
docker compose exec backend python -m scripts.telegram_poll

:: Ver logs del backend en tiempo real
docker compose logs -f backend

:: Ver webhook configurado
curl "https://api.telegram.org/bot<TU_TOKEN>/getWebhookInfo"

:: Eliminar webhook
curl "https://api.telegram.org/bot<TU_TOKEN>/deleteWebhook"

:: Reiniciar backend tras cambios en .env
docker compose restart backend
```

---

## 📚 Referencias

- **Documentación oficial Telegram Bot API**: https://core.telegram.org/bots/api
- **BotFather**: https://t.me/BotFather
- **Levantamiento general del sistema**: `LEVANTAMIENTO.md`
- **Contexto de desarrollo por fases**: `PROGRESO_DESARROLLO.md`
```

---

## 📋 Checklist rápido 
Pasos para replicar el setup, estos son los **5 pasos mínimos**:

```cmd
:: 1. Obtener token de @BotFather
:: 2. Editar .env:
::    TELEGRAM_ENABLED=true
::    TELEGRAM_BOT_TOKEN=<token>
::    TELEGRAM_WEBHOOK_SECRET=<secreto>
docker compose up -d --force-recreate backend

:: 3. Aplicar migración
docker compose exec -T backend alembic upgrade head

:: 4. Iniciar polling (dejar corriendo)
docker compose exec backend python -m scripts.telegram_poll

:: 5. En Telegram, cada operador envía:
::    /vincular <email> <contraseña>
::    (todos los operadores vinculados reciben las notificaciones)
```

Después de eso, enviar `/start` al bot desde cualquier cuenta de Telegram y
empezar a probar el flujo completo (vinculación → consulta → escalamiento).

El documento `TELEGRAM_BOT_SETUP.md` cubre cada uno de estos pasos con
detalle, comandos exactos y troubleshooting para los problemas más comunes.
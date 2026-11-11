# 🤖 Guía de integración del bot de Telegram — Polux Import

Guía paso a paso para activar el canal de Telegram en el sistema de
seguimiento al cliente, con derivación a empleados.

> **Estado previo requerido**: sistema levantado con Fases 0-8 completas
> (ver `LEVANTAMIENTO.md`). Migraciones aplicadas hasta `0007_telegram_channel`.

---

## 📋 Tabla de contenido

1. [Requisitos previos](#1-requisitos-previos)
2. [Crear el bot en BotFather](#2-crear-el-bot-en-botfather)
3. [Configurar variables de entorno](#3-configurar-variables-de-entorno)
4. [Reconstruir backend y aplicar migración](#4-reconstruir-backend-y-aplicar-migración)
5. [Iniciar el bot (polling o webhook)](#5-iniciar-el-bot-polling-o-webhook)
6. [Vincular el operador (notificaciones)](#6-vincular-el-operador-notificaciones)
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

:: Migraciones al día (debe mostrar 0007_telegram_channel como head)
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
- `TELEGRAM_OPERATOR_CHAT_ID=` **vacío** (se llena en el paso 6).

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

**Ahora aplica la migración** `0007_telegram_channel`:

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

## 6. Vincular el operador (notificaciones)

Esta sección configura **qué cuenta de Telegram recibe las notificaciones de casos**.

1. En Telegram, abre tu bot (el que creaste en el paso 2).
2. Envía el comando:
   ```
   /whoami
   ```
3. El bot responderá algo así:
   ```
   Tu chat_id de Telegram es: 123456789

   Envíalo al administrador para recibir notificaciones de casos.
   ```
4. Copia ese `chat_id` (solo los números).
5. Edita `.env`:
   ```env
   TELEGRAM_OPERATOR_CHAT_ID=123456789
   ```
6. Reinicia el backend:
   ```cmd
   docker compose restart backend
   ```

> ✅ **Esto vincula al operador humano**. Cuando un cliente escale (reclamo,
> daño, entrega parcial, retraso crítico), el operador recibirá un mensaje en
> su Telegram con los datos del caso.

> 🔒 Si quieres configurar más de un operador, puedes extender el campo a
> lista separada por comas en el futuro. Por ahora, uno solo.

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

   Para consultar el estado de tu pedido, envíame tu código
   (por ejemplo: PD-2025-0001).

   Si necesitas hablar con un asesor, escribe tu consulta y te derivaré.
   ```
3. Envía el código de un pedido existente:
   ```
   PD-2025-0001
   ```
4. El bot responde:
   ```
   ✅ Vinculado al pedido PD-2025-0001. Ya puedes consultar su estado.
   ```

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
   recibirás una notificación:
   ```
   🚨 Nuevo caso #N · RECLAMO
   Pedido: PD-2025-0001
   Prioridad: ALTA
   Cliente: María Rodríguez
   Descripción: Comunicación entrante detectada como RECLAMO. Escalar sin resolver.
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

---

## 8. Verificar en la base de datos

### Comunicaciones registradas

```cmd
docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "Polux#Strong!Pwd2026" -d PoluxImportDB -Q "SELECT TOP 10 id, canal, direccion, intencion_detectada, estado_entrega, LEFT(contenido, 60) AS contenido FROM comunicacion ORDER BY id DESC;"
```

Debe mostrar comunicaciones con `canal=TELEGRAM`, alternando `ENTRANTE` (del
cliente) y `SALIENTE` (del agente), con `estado_entrega=SENT`.

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
- Enviar `PD-2025-0001` exactamente (mayúsculas).

### El operador no recibe notificaciones

| Causa | Solución |
|---|---|
| `TELEGRAM_OPERATOR_CHAT_ID` vacío | Enviar `/whoami` al bot, copiar el número |
| Chat ID mal copiado (con espacios) | Limpiar el valor en `.env` |
| Backend no reiniciado tras cambiar `.env` | `docker compose restart backend` |
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
docker compose restart backend

:: 3. Aplicar migración
docker compose exec -T backend alembic upgrade head

:: 4. Iniciar polling (dejar corriendo)
docker compose exec backend python -m scripts.telegram_poll

:: 5. En Telegram → /whoami al bot → copiar chat_id
::    Editar .env: TELEGRAM_OPERATOR_CHAT_ID=<chat_id>
docker compose restart backend
```

Después de eso, enviar `/start` al bot desde cualquier cuenta de Telegram y
empezar a probar el flujo completo (vinculación → consulta → escalamiento).

El documento `TELEGRAM_BOT_SETUP.md` cubre cada uno de estos pasos con
detalle, comandos exactos y troubleshooting para los problemas más comunes.
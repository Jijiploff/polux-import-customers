Claro, no necesitas instalar SQL Server en tu máquina para poder gestionarlo gráficamente. Como el motor de base de datos ya está corriendo aislado en un contenedor de Docker, puedes usar cualquier cliente gráfico externo para conectarte a él a través del puerto que ya está expuesto en tu `localhost`.

La clave está en usar el **puerto correcto** y la **autenticación de SQL** (usuario `sa`).

### 🔌 Datos de conexión

Independientemente de la herramienta que elijas, estos son los parámetros que necesitas para conectarte:

| Parámetro | Valor a usar |
| :--- | :--- |
| **Servidor / Host** | `localhost` o `127.0.0.1` |
| **Puerto** | `1433` (a menos que lo hayas cambiado por un conflicto) |
| **Autenticación** | **SQL Server Authentication** (no Windows Authentication) |
| **Usuario** | `sa` |
| **Contraseña** | La que definiste en tu archivo `.env` (ej. `Polux#Strong!Pwd2025`) |
| **Base de Datos** | `PoluxImportDB` (o puedes conectarte a `master` primero) |

> **Nota sobre el puerto**: Si en tu `docker-compose.yml` mapeaste el puerto a `14330:1433` (porque tenías otro SQL Server local ocupando el 1433), entonces en el campo "Puerto" de tu cliente debes usar **`14330`**.

---

### 🛠️ Herramientas gráficas recomendadas

Aquí tienes tres excelentes opciones, ordenadas de más a menos específica para SQL Server. Todas son gratuitas y funcionan perfectamente con tu contenedor.

#### 1. SQL Server Management Studio (SSMS) - La oficial

Es la herramienta nativa de Microsoft para administrar SQL Server. Es la más completa, aunque solo está disponible para Windows.

*   **Descarga**: [SSMS (Microsoft)](https://learn.microsoft.com/en-us/sql/ssms/download-sql-server-management-studio-ssms)
*   **Cómo conectarse**:
    1.  Abre SSMS. En la ventana de conexión, en **"Nombre del servidor"**, escribe `localhost,1433` (usa una **coma**, no dos puntos).
    2.  En **"Autenticación"**, selecciona **"Autenticación de SQL Server"**.
    3.  Ingresa el usuario `sa` y la contraseña de tu `.env`.
    4.  (Opcional) Haz clic en "Opciones" > "Propiedades de conexión" y escribe `PoluxImportDB` como base de datos.
    5.  Haz clic en **"Conectar"**.

    El Flujo Ideal (Cómo DEBE interactuar el bot)
Cliente: Hola, quiero saber el estado de mis pedidos.

Bot: ¡Hola María! Veo que tienes 2 pedidos activos en este momento: 1️⃣ **PD-2025-0001** (AirPods Pro 2) 2️⃣ **PD-2025-0002** (iPhone 15 Pro Max + AirPods Pro 2) ¿De cuál de ellos te gustaría saber el estado? (Puedes escribir el número o el código) (NOTA: debe listar cuando se mencione ver estado, confirmar la entre de un pedido, etc)

Cliente: 2 (o 2️⃣ o PD-2025-0002)(NOTA: debe entender y consultar al pedido indicado)

Bot: Perfecto, ahora estamos consultando el pedido **PD-2025-0002**. ¿Qué deseas saber sobre él?

Cliente: ¿A qué hora llega mi iPhone?

Bot: El iPhone 15 Pro Max de tu pedido **PD-2025-0002** llegará a aduana el 23/11/2026, con entrega estimada para el 07/12/2026. ¿Te gustaría coordinar la entrega?

Cliente: Mejor dime del otro pedido/PD-2025-0001/1 etc (NOTA: debe cambiar a otro pedido cuando se solicite o indicar q no hay otro pedido a nombre del usuario si no hay mas de 1)

Bot: ✅ Cambiando al pedido **PD-2025-0001**. Tus AirPods Pro 2 están listos. La entrega está programada para el 16/11/2026, entre 13:00 y 15:00 hrs en Calle San Carlos 501. ¿Todo correcto?

2. Diagnóstico Técnico (Por qué fallaba)
No hay memoria de contexto: Siempre se busca el pedido más reciente en la base de datos (el 0001). Si en el mensaje 3 el cliente pregunta algo, el bot vuelve a leer los datos del 0001, ignorando que ya se había cambiado al 0002.

No intercepta los códigos cortos: El bot solo detecta cambios de pedido si el cliente envía el código completo y el DNI juntos. Si escribes solo "2" o "0002", pasa hacia la IA. La IA ve un número suelto y se confunde, o responde con los datos del pedido por defecto.

Falta de reglas en el Prompt: La IA no listar oportunamente los pedidos en formato numerado (1️⃣, 2️⃣) cuando hay más de uno, ni de pedirle al cliente que elija.
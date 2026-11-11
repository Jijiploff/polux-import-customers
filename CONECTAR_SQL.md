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
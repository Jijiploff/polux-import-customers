# Polux Import · Fase Customers — Despliegue productivo

## 1. Requisitos
- Docker Engine 24+ con Compose v2
- 4 vCPU / 8 GB RAM (recomendado)
- 30 GB disco (SQL Server + backups + logs)
- Dominio público (para webhook Meta) y certificado TLS (Nginx delante o Cloudflare)

## 2. Preparación del entorno

```bash
git clone <repo> polux-import-customers
cd polux-import-customers

cp .env.prod.example .env
# Editar .env con:
#  - MSSQL_SA_PASSWORD: contraseña fuerte (cumple política SQL Server)
#  - JWT_SECRET_KEY: secreto aleatorio ≥ 64 caracteres
#  - WHATSAPP_*: credenciales reales de Meta
#  - EMAIL_*: proveedor de correo (Resend o SMTP)
#  - LLM_API_KEY: si se usa proveedor real
#  - CORS_ORIGINS: dominio exacto del frontend
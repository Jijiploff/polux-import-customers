#!/usr/bin/env bash
# Backup de PoluxImportDB a ./backups/
set -euo pipefail

: "${MSSQL_SA_PASSWORD:?Falta MSSQL_SA_PASSWORD}"
DB_NAME="${DB_NAME:-PoluxImportDB}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
FILE="PoluxImportDB_${STAMP}.bak"

mkdir -p backups

docker compose -f docker-compose.prod.yml exec -T db /opt/mssql-tools18/bin/sqlcmd \
    -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" \
    -Q "BACKUP DATABASE [$DB_NAME] TO DISK = N'/var/opt/mssql/backups/${FILE}' WITH INIT, COMPRESSION;"

echo "[backup] OK → backups/${FILE}"

# Conservar solo 14 días
find backups -name 'PoluxImportDB_*.bak' -mtime +14 -delete || true
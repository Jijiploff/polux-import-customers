#!/usr/bin/env bash
# Restaura un .bak específico.
# Uso: ./scripts/restore.sh backups/PoluxImportDB_20250101T000000Z.bak
set -euo pipefail

: "${MSSQL_SA_PASSWORD:?Falta MSSQL_SA_PASSWORD}"
: "${1:?Uso: $0 <archivo.bak>}"

BAK_FILE="$1"
DB_NAME="${DB_NAME:-PoluxImportDB}"

if [ ! -f "$BAK_FILE" ]; then
    echo "No existe: $BAK_FILE" >&2
    exit 1
fi

FILENAME=$(basename "$BAK_FILE")

docker compose -f docker-compose.prod.yml exec -T db /opt/mssql-tools18/bin/sqlcmd \
    -C -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "
        ALTER DATABASE [$DB_NAME] SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
        RESTORE DATABASE [$DB_NAME] FROM DISK = N'/var/opt/mssql/backups/${FILENAME}' WITH REPLACE;
        ALTER DATABASE [$DB_NAME] SET MULTI_USER;
    "

echo "[restore] OK ← $BAK_FILE"
# Reemplaza el bloque anterior. Añade test-data y db-reset (ya añadidos en Fase 1).
# Este Makefile reemplaza al de Fase 1.
.PHONY: up down logs build sh-backend sh-db init-db migrate revision seed test-data db-reset test

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

sh-backend:
	docker compose exec backend bash

sh-db:
	docker compose exec db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$$MSSQL_SA_PASSWORD"

init-db:
	docker compose exec -T db /opt/mssql-tools18/bin/sqlcmd -C -S localhost -U sa -P "$$MSSQL_SA_PASSWORD" \
		-Q "IF DB_ID('PoluxImportDB') IS NULL CREATE DATABASE PoluxImportDB"

migrate:
	docker compose exec backend alembic upgrade head

revision:
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

seed:
	docker compose exec backend python -m scripts.seed_data

test-data:
	docker compose exec backend python -m scripts.test_data

db-reset:
	docker compose exec backend alembic downgrade base
	docker compose exec backend alembic upgrade head
	docker compose exec backend python -m scripts.seed_data
	docker compose exec backend python -m scripts.test_data

test:
	docker compose exec backend pytest -q
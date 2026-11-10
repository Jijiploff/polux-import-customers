# Polux Import · Fase Customers

Sistema de seguimiento y atención al cliente (agente IA + gestión web + dashboard).

## Requisitos
- Docker Desktop 4.x o Docker Engine + Compose v2
- 4 GB de RAM disponibles

## Puesta en marcha

```bash
cp .env.example .env
make up                     # levanta db + backend + frontend
make init-db                # crea PoluxImportDB si no existe
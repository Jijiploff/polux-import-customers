"""Audita la presencia y compilación de todos los módulos del backend.

Uso:
    python -m scripts.verify_modules
Devuelve exit 0 si todo está OK, 1 si falta algún módulo o no importa.
"""
from __future__ import annotations

import importlib
import sys

MODULOS_REQUERIDOS: list[str] = [
    # core
    "app.main",
    "app.core.config",
    "app.core.logging",
    "app.core.security",
    "app.core.deps",
    "app.core.rate_limit",
    # db
    "app.db.base",
    "app.db.session",
    # models
    "app.models",
    "app.models.base_mixins",
    "app.models.core",
    "app.models.orders",
    "app.models.comms",
    "app.models.delivery",
    "app.models.analytics",
    # schemas
    "app.schemas.auth",
    "app.schemas.common",
    "app.schemas.pedido",
    "app.schemas.entrega",
    "app.schemas.comms",
    "app.schemas.admin",
    "app.schemas.agent",
    # services
    "app.services.pedido_service",
    "app.services.hito_service",
    "app.services.entrega_service",
    "app.services.caso_service",
    "app.services.template_renderer",
    "app.services.notification_service",
    "app.services.rule_engine",
    "app.services.scheduler",
    "app.services.llm_provider",
    "app.services.agent_service",
    "app.services.whatsapp_service",
    "app.services.email_service",
    "app.services.outbox_worker",
    "app.services.fact_sync_service",
    "app.services.kpi_service",
    # routers
    "app.api.v1.router",
    "app.api.v1.health",
    "app.api.v1.auth",
    "app.api.v1.usuarios",
    "app.api.v1.pedidos",
    "app.api.v1.items",
    "app.api.v1.hitos",
    "app.api.v1.entregas",
    "app.api.v1.casos",
    "app.api.v1.imprevistos",
    "app.api.v1.comunicaciones",
    "app.api.v1.alertas",
    "app.api.v1.reglas",
    "app.api.v1.catalogos",
    "app.api.v1.kpis",
    "app.api.v1.dashboard",
    "app.api.v1.admin",
    "app.api.v1.agent",
    "app.api.v1.outbox",
    "app.api.v1.webhooks",
    # scripts
    "scripts.seed_data",
    "scripts.test_data",
    "scripts.run_worker",
    "scripts.verify_kpis",
]


def main() -> int:
    fallos: list[tuple[str, str]] = []
    for mod in MODULOS_REQUERIDOS:
        try:
            importlib.import_module(mod)
        except Exception as exc:
            fallos.append((mod, f"{type(exc).__name__}: {exc}"))

    print(f"Módulos verificados: {len(MODULOS_REQUERIDOS) - len(fallos)}/{len(MODULOS_REQUERIDOS)}")
    if fallos:
        print("\nMódulos con error:")
        for mod, err in fallos:
            print(f"  ✗ {mod}: {err}")
        return 1

    # Invariantes de contrato mínimos (fail-fast si un refactor los rompe)
    invariantes: list[tuple[str, bool]] = []
    try:
        from app.services.rule_engine import RuleEngine

        invariantes.append(
            ("RuleEngine.run_all invoca registrar_atrasos",
             "registrar_atrasos" in RuleEngine.run_all.__code__.co_names),
        )
    except Exception as exc:
        invariantes.append((f"RuleEngine.run_all inspección: {exc}", False))

    try:
        from app.schemas.pedido import ItemHitoRead

        invariantes.append(
            ("ItemHitoRead._fill_hito_fields existe",
             hasattr(ItemHitoRead, "_fill_hito_fields")),
        )
    except Exception as exc:
        invariantes.append((f"ItemHitoRead inspección: {exc}", False))

    print("\nInvariantes:")
    for nombre, ok in invariantes:
        print(f"  {'✓' if ok else '✗'} {nombre}")
    if not all(ok for _, ok in invariantes):
        return 1

    print("\nTodos los módulos importan y las invariantes se cumplen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
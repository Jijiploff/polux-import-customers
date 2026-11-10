"""Casos e imprevistos: creación y primera acción.

Usa un pedido de prueba propio para no depender del estado de los
pedidos demo ni dejar residuo en ellos.
"""
from datetime import datetime

from app.db.session import SessionLocal
from tests.db_utils import cleanup_pedido, crear_pedido_listo


def test_crear_caso_e_imprevisto(client, auth):
    db = SessionLocal()
    try:
        ped, _, _ = crear_pedido_listo(db)
        pid = ped.id
    finally:
        db.close()
    try:
        caso = client.post(
            "/api/v1/casos",
            headers=auth["operador"],
            json={"pedido_id": pid, "motivo": "RECLAMO",
                  "descripcion": "Cliente reclama retraso", "prioridad": "ALTA"},
        )
        assert caso.status_code == 200

        imp = client.post(
            "/api/v1/imprevistos",
            headers=auth["operador"],
            json={"pedido_id": pid, "tipo": "OPERATIVO",
                  "descripcion": "Producto dañado en bodega",
                  "fecha_deteccion": datetime.utcnow().isoformat()},
        )
        assert imp.status_code == 200
        imp_id = imp.json()["id"]
        upd = client.patch(
            f"/api/v1/imprevistos/{imp_id}",
            headers=auth["operador"],
            json={"estado": "RESUELTO", "resolucion": "Reemplazado"},
        )
        assert upd.status_code == 200
        assert upd.json()["estado"] == "RESUELTO"
    finally:
        db = SessionLocal()
        try:
            cleanup_pedido(db, pid)
        finally:
            db.close()

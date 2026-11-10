"""Marcado de hitos completados: propaga estado del ítem y del pedido."""
from datetime import datetime

from app.db.session import SessionLocal
from tests.db_utils import cleanup_pedido, crear_pedido_listo


def test_marcar_completado(client, auth):
    # Pedido de prueba propio (los pedidos demo ya tienen hitos completados
    # y/o están cerrados → 409).
    db = SessionLocal()
    try:
        ped, item, ih = crear_pedido_listo(db, con_hito=True)
        pid, item_id, hito_id = ped.id, item.id, ih.id
    finally:
        db.close()
    try:
        hitos = client.get(
            f"/api/v1/hitos/por-item/{item_id}", headers=auth["operador"]
        ).json()
        assert hitos, "El pedido de prueba debe tener al menos un hito"
        assert hitos[0]["id"] == hito_id

        r = client.post(
            f"/api/v1/hitos/{hito_id}/completar",
            headers=auth["operador"],
            json={"fecha_real": datetime.utcnow().isoformat()},
        )
        assert r.status_code == 200
        assert r.json()["estado"] == "COMPLETADO"
    finally:
        db = SessionLocal()
        try:
            cleanup_pedido(db, pid)
        finally:
            db.close()

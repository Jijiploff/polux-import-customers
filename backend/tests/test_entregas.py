"""Pruebas de la regla inviolable: entrega parcial requiere autorización humana.

Cada test crea su propio pedido de prueba (nunca opera sobre los pedidos
demo, que están cerrados/devuelven 409) y lo borra al terminar.
"""
from datetime import datetime

from app.db.session import SessionLocal
from tests.db_utils import cleanup_pedido, crear_pedido_listo


def _nuevo_pedido_listo():
    """Devuelve (pedido_id, item_id) de un pedido fresco LISTO_PARA_ENTREGA."""
    db = SessionLocal()
    try:
        ped, item, _ = crear_pedido_listo(db)
        return ped.id, item.id
    finally:
        db.close()


def _borrar(pedido_id: int) -> None:
    db = SessionLocal()
    try:
        cleanup_pedido(db, pedido_id)
    finally:
        db.close()


def test_entrega_parcial_sin_autorizacion_falla(client, auth):
    pid, item_id = _nuevo_pedido_listo()
    try:
        r = client.post(
            "/api/v1/entregas",
            headers=auth["operador"],
            json={
                "pedido_id": pid,
                "tipo": "PARCIAL",
                "modalidad": "DOMICILIO",
                "fecha_programada": datetime.utcnow().isoformat(),
                "pedido_item_ids": [item_id],
            },
        )
        assert r.status_code == 400
        assert "autoriz" in r.json()["detail"].lower()
    finally:
        _borrar(pid)


def test_entrega_completa_ok_y_conformidad(client, auth):
    pid, item_id = _nuevo_pedido_listo()
    try:
        r = client.post(
            "/api/v1/entregas",
            headers=auth["operador"],
            json={
                "pedido_id": pid,
                "tipo": "COMPLETA",
                "modalidad": "DOMICILIO",
                "fecha_programada": datetime.utcnow().isoformat(),
            },
        )
        assert r.status_code == 201
        entrega = r.json()
        confs = [
            {
                "pedido_item_id": item_id,
                "checklist_caja_sellada": True,
                "checklist_modelo_ok": True,
                "checklist_color_ok": True,
                "checklist_capacidad_ok": True,
                "checklist_imei_ok": True,
                "checklist_accesorios_ok": True,
                "resultado": "CONFORME",
            }
        ]
        r2 = client.post(
            f"/api/v1/entregas/{entrega['id']}/completar",
            headers=auth["operador"],
            json={"fecha_real": datetime.utcnow().isoformat(), "conformidades": confs},
        )
        assert r2.status_code == 200
        assert r2.json()["estado"] == "ENTREGADA"
    finally:
        _borrar(pid)

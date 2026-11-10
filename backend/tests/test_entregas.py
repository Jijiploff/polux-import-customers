"""Pruebas de la regla inviolable: entrega parcial requiere autorización humana."""
from datetime import datetime


def _get_pedido_listo(client, auth):
    """Devuelve el primer pedido con todos los ítems LISTO_PARA_ENTREGA, o None."""
    r = client.get("/api/v1/pedidos?size=50", headers=auth["operador"])
    for p in r.json().get("items", []):
        detalle = client.get(f"/api/v1/pedidos/{p['id']}/full", headers=auth["operador"]).json()
        if all(i["estado"] == "LISTO_PARA_ENTREGA" for i in detalle["items"]):
            return detalle
    return None


def _preparar_pedido_listo(client, auth):
    """Fuerza todos los ítems del pedido a LISTO_PARA_ENTREGA vía PATCH."""
    r = client.get("/api/v1/pedidos?size=1", headers=auth["operador"])
    items = r.json().get("items", [])
    if not items:
        return None
    pid = items[0]["id"]
    detalle = client.get(f"/api/v1/pedidos/{pid}/full", headers=auth["operador"]).json()
    for it in detalle["items"]:
        client.patch(
            f"/api/v1/items/{it['id']}/estado",
            headers=auth["operador"],
            json={"estado": "LISTO_PARA_ENTREGA"},
        )
    return client.get(f"/api/v1/pedidos/{pid}/full", headers=auth["operador"]).json()


def test_entrega_parcial_sin_autorizacion_falla(client, auth):
    pedido = _preparar_pedido_listo(client, auth)
    if not pedido:
        return
    item_id = pedido["items"][0]["id"]
    r = client.post(
        "/api/v1/entregas",
        headers=auth["operador"],
        json={
            "pedido_id": pedido["id"],
            "tipo": "PARCIAL",
            "modalidad": "DOMICILIO",
            "fecha_programada": datetime.utcnow().isoformat(),
            "pedido_item_ids": [item_id],
        },
    )
    assert r.status_code == 400
    assert "autoriz" in r.json()["detail"].lower()


def test_entrega_completa_ok_y_conformidad(client, auth):
    pedido = _preparar_pedido_listo(client, auth)
    if not pedido:
        return
    r = client.post(
        "/api/v1/entregas",
        headers=auth["operador"],
        json={
            "pedido_id": pedido["id"],
            "tipo": "COMPLETA",
            "modalidad": pedido["modalidad_entrega"],
            "fecha_programada": datetime.utcnow().isoformat(),
        },
    )
    assert r.status_code == 201
    entrega = r.json()
    # Registrar conformidad
    confs = [
        {
            "pedido_item_id": it["id"],
            "checklist_caja_sellada": True,
            "checklist_modelo_ok": True,
            "checklist_color_ok": True,
            "checklist_capacidad_ok": True,
            "checklist_imei_ok": True,
            "checklist_accesorios_ok": True,
            "resultado": "CONFORME",
        }
        for it in pedido["items"]
    ]
    r2 = client.post(
        f"/api/v1/entregas/{entrega['id']}/completar",
        headers=auth["operador"],
        json={"fecha_real": datetime.utcnow().isoformat(), "conformidades": confs},
    )
    assert r2.status_code == 200
    assert r2.json()["estado"] == "ENTREGADA"
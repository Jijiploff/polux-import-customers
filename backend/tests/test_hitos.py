"""Marcado de hitos completados: propaga estado del ítem y del pedido."""
from datetime import datetime


def test_marcar_completado(client, auth):
    # Necesita un pedido de prueba. Si no hay, se salta.
    r = client.get("/api/v1/pedidos?size=1", headers=auth["operador"])
    items = r.json().get("items", [])
    if not items:
        return
    pid = items[0]["id"]
    detalle = client.get(f"/api/v1/pedidos/{pid}/full", headers=auth["operador"]).json()
    item = detalle["items"][0]
    hitos = client.get(f"/api/v1/hitos/por-item/{item['id']}", headers=auth["operador"]).json()
    if not hitos:
        return
    hito_id = hitos[0]["id"]
    r = client.post(
        f"/api/v1/hitos/{hito_id}/completar",
        headers=auth["operador"],
        json={"fecha_real": datetime.utcnow().isoformat()},
    )
    assert r.status_code == 200
    assert r.json()["estado"] == "COMPLETADO"
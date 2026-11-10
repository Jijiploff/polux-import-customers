"""Listados y detalle de pedidos."""
def test_listar_pedidos(client, auth):
    r = client.get("/api/v1/pedidos", headers=auth["operador"])
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body


def test_detalle_pedido(client, auth):
    # Requiere que `make test-data` se haya ejecutado; en CI se puede omitir con skip.
    r = client.get("/api/v1/pedidos?size=1", headers=auth["operador"])
    items = r.json().get("items", [])
    if not items:
        return  # sin datos aún
    pid = items[0]["id"]
    r2 = client.get(f"/api/v1/pedidos/{pid}", headers=auth["operador"])
    assert r2.status_code == 200
    assert r2.json()["id"] == pid
"""Casos e imprevistos: creación y primera acción."""
from datetime import datetime


def test_crear_caso_e_imprevisto(client, auth):
    r = client.get("/api/v1/pedidos?size=1", headers=auth["operador"])
    items = r.json().get("items", [])
    if not items:
        return
    pid = items[0]["id"]

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
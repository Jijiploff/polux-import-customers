"""Los KPIs se exponen y provienen de SQL (no de IA)."""
def test_kpis_disponibles(client, auth):
    for path in [
        "/api/v1/kpis/actualizacion-cliente",
        "/api/v1/kpis/resolucion-automatica",
        "/api/v1/kpis/tiempo-respuesta-escalados",
        "/api/v1/kpis/resolucion-imprevistos",
        "/api/v1/kpis/entregas-a-tiempo",
        "/api/v1/kpis/entregas-sin-observaciones",
        "/api/v1/kpis/entregas-parciales",
    ]:
        r = client.get(path, headers=auth["gerente"])
        assert r.status_code == 200
        assert "codigo" in r.json()


def test_dashboard_resumen(client, auth):
    r = client.get("/api/v1/dashboard/resumen", headers=auth["gerente"])
    assert r.status_code == 200
    assert "actualizacion_cliente" in r.json()


def test_dashboard_no_operador(client, auth):
    r = client.get("/api/v1/dashboard/resumen", headers=auth["operador"])
    assert r.status_code == 403
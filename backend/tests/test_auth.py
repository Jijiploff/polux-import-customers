"""Auth: login OK, login inválido y guarda por roles."""
def test_login_ok(client):
    # Requiere que el seed haya corrido; si no, se crea vía conftest al pedir tokens.
    r = client.post("/api/v1/auth/login",
                    json={"email": "admin@poluximport.pe", "password": "Admin123!"})
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert "ADMIN" in body["roles"]


def test_login_invalido(client):
    r = client.post("/api/v1/auth/login",
                    json={"email": "admin@poluximport.pe", "password": "xxx"})
    assert r.status_code == 401


def test_endpoint_protegido_sin_token(client):
    r = client.get("/api/v1/pedidos")
    assert r.status_code == 401


def test_gerente_no_puede_crear_usuarios(client, auth):
    r = client.post("/api/v1/usuarios", headers=auth["gerente"],
                    json={"email": "nuevo@example.com", "nombre_completo": "N", "password": "Abc12345!", "roles": ["OPERADOR"]})
    assert r.status_code == 403
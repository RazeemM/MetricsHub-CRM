"""The API description and interactive docs are published under /api (reachable through nginx)."""


def test_openapi_and_docs_under_api(client):
    spec = client.get("/api/openapi.json")
    assert spec.status_code == 200
    body = spec.json()
    assert "/api/opportunities" in body["paths"] and "/api/licences/renewals" in body["paths"]
    assert body["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"] == \
        "/api/auth/login"
    docs = client.get("/api/docs")
    assert docs.status_code == 200 and "/api/openapi.json" in docs.text
    assert client.get("/api/redoc").status_code == 200
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404

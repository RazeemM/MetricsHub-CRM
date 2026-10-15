import os

os.environ.setdefault("CRM_RUN_SCHEDULER", "false")
os.environ.setdefault("CRM_DATABASE_URL", "postgresql+psycopg://crm:crm@localhost:5432/crm_test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402,F401
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        token = c.post("/api/auth/login", data={"username": "admin@example.com", "password": "admin123"}).json()
        c.headers["Authorization"] = f"Bearer {token['access_token']}"
        yield c


@pytest.fixture(scope="session")
def ref(client):
    brands = {b["code"]: b["id"] for b in client.get("/api/brands").json()}
    pipelines = {p["kind"]: p for p in client.get("/api/pipelines").json()}
    products = {p["sku"]: p for p in client.get("/api/products").json()}
    books = {b["name"]: b for b in client.get("/api/price-books").json()}
    return {"brands": brands, "pipelines": pipelines, "products": products, "books": books}

import io
import json
from decimal import Decimal

from openpyxl import Workbook


def _account(client, name="Acme Bank", **kw):
    r = client.post("/api/accounts", json={"name": name, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_auth_required(client):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as anon:
        assert anon.get("/api/accounts").status_code == 401


def test_bad_login(client):
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as anon:
        r = anon.post("/api/auth/login", data={"username": "admin@example.com", "password": "nope"})
        assert r.status_code == 401


def test_account_and_contact_crud(client):
    acc = _account(client, "Contoso", domain="https://www.contoso.com/", country="France")
    assert acc["domain"] == "contoso.com"
    r = client.post("/api/contacts", json={"first_name": "Jane", "last_name": "Doe", "email": "Jane@Contoso.com",
                                           "account_id": acc["id"]})
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["email"] == "jane@contoso.com" and c["full_name"] == "Jane Doe"
    dup = client.post("/api/contacts", json={"email": "JANE@contoso.com"})
    assert dup.status_code == 409
    r = client.patch(f"/api/contacts/{c['id']}", json={"lifecycle": "qualified", "consent_marketing": True})
    assert r.json()["lifecycle"] == "qualified" and r.json()["consent_at"]
    assert client.get("/api/accounts", params={"q": "conto"}).json()["items"][0]["contact_count"] == 1
    assert client.get("/api/search", params={"q": "jane"}).json()["contacts"][0]["id"] == c["id"]


def test_opportunity_pricing_and_stages(client, ref):
    acc = _account(client, "Big Telco", account_type="prospect")
    datadog = client.get("/api/accounts", params={"q": "datadog"}).json()["items"][0]
    am = client.post("/api/contacts", json={"first_name": "Sam", "last_name": "Rep", "email": "sam@datadoghq.com",
                                            "account_id": datadog["id"], "role": "platform_account_manager"}).json()
    payload = {
        "title": "Big Telco - 500 servers",
        "account_id": acc["id"],
        "brand_id": ref["brands"]["METRICSHUB"],
        "lead_source": "platform_referral",
        "referring_platform_id": datadog["id"],
        "partner_contact_id": am["id"],
        "route_to_market": "marketplace",
        "contract_start": "2026-11-01",
        "term_months": 24,
        "line_items": [
            {"product_id": ref["products"]["MH-ENT-HOST"]["id"], "quantity": 500, "discount_pct": 20},
            {"product_id": ref["products"]["MH-PS-DAY"]["id"], "quantity": 3, "unit_price": "1200"},
        ],
    }
    r = client.post("/api/opportunities", json=payload)
    assert r.status_code == 201, r.text
    o = r.json()
    # 500 x 15 x 24 x 0.8 = 144,000 + 3,600 services
    assert Decimal(o["amount_tcv"]) == Decimal("147600.00")
    assert Decimal(o["amount_arr"]) == Decimal("72000.00")
    assert o["contract_end"] == "2028-10-31"
    assert o["stage"]["name"] == "New" and o["currency"] == "USD"
    assert o["partner_contact"]["id"] == am["id"]

    stages = {s["name"]: s["id"] for s in ref["pipelines"]["new_business"]["stages"]}
    r = client.post(f"/api/opportunities/{o['id']}/stage", json={"stage_id": stages["Lost"]})
    assert r.status_code == 422  # lost reason required
    r = client.post(f"/api/opportunities/{o['id']}/stage", json={"stage_id": stages["Won"]})
    assert r.json()["closed_at"] and r.json()["effective_probability"] == 100
    assert client.get(f"/api/accounts/{acc['id']}").json()["account_type"] == "customer"

    # update quantity → recompute
    r = client.patch(f"/api/opportunities/{o['id']}", json={"line_items": [
        {"product_id": ref["products"]["MH-ENT-HOST"]["id"], "quantity": 100}]})
    assert Decimal(r.json()["amount_tcv"]) == Decimal("36000.00")

    board = client.get("/api/opportunities/board").json()
    assert [c["stage"]["name"] for c in board["columns"]][0] == "New"
    dash = client.get("/api/dashboard").json()
    assert "pipeline" in dash and "by_platform" in dash


def test_missing_price_requires_manual_price(client, ref):
    acc = _account(client, "NoPrice Corp")
    r = client.post("/api/opportunities", json={
        "title": "x", "account_id": acc["id"], "brand_id": ref["brands"]["METRICSHUB"],
        "line_items": [{"product_id": ref["products"]["MH-PREMIER-SUP"]["id"], "quantity": 1}]})
    assert r.status_code == 422


def test_price_preview(client, ref):
    r = client.post("/api/opportunities/price-preview", json={
        "term_months": 12, "price_book_id": ref["books"]["MetricsHub Direct USD"]["id"],
        "line_items": [{"product_id": ref["products"]["MH-ENT-HOST"]["id"], "quantity": 10}]})
    assert Decimal(r.json()["tcv"]) == Decimal("1800.00")


def test_import_contacts_xlsx_and_export(client):
    wb = Workbook()
    ws = wb.active
    ws.append(["Full Name", "E-mail", "Company", "Job Title", "Country", "Lead Source"])
    ws.append(["Alice Martin", "alice@globex.com", "Globex", "CIO", "France", "Download"])
    ws.append(["Bob Smith", "bob@globex.com", "", "SRE", "USA", ""])
    ws.append(["", "not-an-email", "X", "", "", ""])
    ws.append(["Jane Doe", "jane@contoso.com", "Contoso", "CTO", "", ""])  # existing → update
    buf = io.BytesIO()
    wb.save(buf)

    files = {"file": ("leads.xlsx", buf.getvalue(),
                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    prev = client.post("/api/imports/preview", data={"entity": "contacts"}, files=files).json()
    m = prev["suggested_mapping"]
    assert m["full_name"] == "Full Name" and m["email"] == "E-mail" and m["company"] == "Company"
    assert prev["total_rows"] == 4

    res = client.post("/api/imports/commit", data={"entity": "contacts", "mapping": json.dumps(m)},
                      files=files).json()
    assert (res["created"], res["updated"], res["skipped"]) == (2, 1, 1), res
    bob = client.get("/api/contacts", params={"q": "bob@globex.com"}).json()["items"][0]
    assert bob["account"]["name"] == "Globex"  # matched by email domain
    alice = client.get("/api/contacts", params={"q": "alice"}).json()["items"][0]
    assert alice["source"] == "download"

    r = client.get("/api/export/contacts", params={"fmt": "csv"})
    assert r.status_code == 200 and "alice@globex.com" in r.text
    r = client.get("/api/export/opportunities")
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")


def test_import_accounts_csv(client):
    csv_data = "Account Name;Website;Type;Country\nInitech;https://initech.io;Customer;Germany\nInitech;;;\n"
    files = {"file": ("accounts.csv", csv_data.encode(), "text/csv")}
    prev = client.post("/api/imports/preview", data={"entity": "accounts"}, files=files).json()
    res = client.post("/api/imports/commit", data={"entity": "accounts",
                                                   "mapping": json.dumps(prev["suggested_mapping"])},
                      files=files).json()
    assert res["created"] == 1 and res["updated"] == 1
    acc = client.get("/api/accounts", params={"q": "initech"}).json()["items"][0]
    assert acc["account_type"] == "customer" and acc["domain"] == "initech.io"


def test_activities(client):
    acc = _account(client, "Task Co")
    r = client.post("/api/activities", json={"type": "task", "subject": "Send pricing", "account_id": acc["id"],
                                             "due_at": "2026-10-20T09:00:00Z"})
    assert r.status_code == 201
    tasks = client.get("/api/activities", params={"open_tasks": True}).json()
    assert tasks["total"] >= 1


def test_readonly_user_cannot_write(client):
    client.post("/api/users", json={"email": "viewer@example.com", "full_name": "Viewer", "role": "readonly",
                                    "password": "viewer123"})
    from fastapi.testclient import TestClient

    from app.main import app
    with TestClient(app) as c:
        t = c.post("/api/auth/login", data={"username": "viewer@example.com", "password": "viewer123"}).json()
        c.headers["Authorization"] = f"Bearer {t['access_token']}"
        assert c.get("/api/accounts").status_code == 200
        assert c.post("/api/accounts", json={"name": "Nope"}).status_code == 403

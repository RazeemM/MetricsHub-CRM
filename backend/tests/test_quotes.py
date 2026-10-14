import datetime as dt
from decimal import Decimal


def _opp(client, ref, brand="METRICSHUB", sku="MH-ENT-HOST", qty=10):
    acc = client.post("/api/accounts", json={"name": f"Quote Co {brand}{qty}", "address": "1 <b>Main</b> St"}).json()
    c = client.post("/api/contacts", json={"first_name": "Q", "last_name": "Buyer", "email": f"q{brand}{qty}@quoteco.example",
                                           "account_id": acc["id"]}).json()
    r = client.post("/api/opportunities", json={
        "title": "Quote test", "account_id": acc["id"], "brand_id": ref["brands"][brand], "primary_contact_id": c["id"],
        "line_items": [{"product_id": ref["products"][sku]["id"], "quantity": qty}]})
    assert r.status_code == 201, r.text
    return r.json()


def test_every_product_has_a_placeholder_price(client, ref):
    for p in client.get("/api/products").json():
        if p["sku"].startswith("TEST-"):
            continue
        assert p["prices"], f"{p['sku']} has no price"


def test_templates_seeded_per_brand(client):
    tpls = {t["brand_name"]: t for t in client.get("/api/quote-templates").json()}
    assert set(tpls) == {"MetricsHub", "Sentry Software"}
    assert tpls["Sentry Software"]["logo_data_uri"].startswith("data:image/png;base64,")
    assert tpls["Sentry Software"]["header_show_name"] is False


def test_quote_numbering_versions_and_pdf(client, ref):
    o1 = _opp(client, ref, qty=10)
    o2 = _opp(client, ref, qty=20)
    q1 = client.post(f"/api/opportunities/{o1['id']}/quotes", json={}).json()
    q1b = client.post(f"/api/opportunities/{o1['id']}/quotes", json={"valid_days": 10, "notes": "x"}).json()
    q2 = client.post(f"/api/opportunities/{o2['id']}/quotes", json={}).json()
    year = dt.date.today().year
    assert q1["number"] == f"MH-Q-{year}-0001" and q1["version"] == 1
    assert q1b["number"] == q1["number"] and q1b["display_number"].endswith("v2")
    assert q2["number"] == f"MH-Q-{year}-0002"
    assert q1b["valid_until"] == (dt.date.today() + dt.timedelta(days=10)).isoformat()
    assert Decimal(q1["amount_tcv"]) == Decimal("1800.00")

    s = _opp(client, ref, brand="SENTRY", sku="SEN-BHOM-BUNDLE", qty=5)
    qs = client.post(f"/api/opportunities/{s['id']}/quotes", json={}).json()
    assert qs["number"] == f"SEN-Q-{year}-0001"

    r = client.get(f"/api/quotes/{q1['id']}/pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    html = client.get(f"/api/quotes/{q1['id']}/html").text
    assert "Q Buyer" in html and "&lt;b&gt;Main&lt;/b&gt;" in html  # customer data is escaped
    assert len(client.get(f"/api/opportunities/{o1['id']}/quotes").json()) == 2


def test_quote_is_a_snapshot(client, ref):
    o = _opp(client, ref, qty=30)
    q = client.post(f"/api/opportunities/{o['id']}/quotes", json={}).json()
    client.patch(f"/api/opportunities/{o['id']}", json={"line_items": [
        {"product_id": ref["products"]["MH-ENT-HOST"]["id"], "quantity": 999}]})
    html = client.get(f"/api/quotes/{q['id']}/html").text
    assert "999 host" not in html and "30 host" in html


def test_quote_requires_lines_and_status_rules(client, ref):
    acc = client.post("/api/accounts", json={"name": "Empty deal co"}).json()
    o = client.post("/api/opportunities", json={"title": "empty", "account_id": acc["id"],
                                                "brand_id": ref["brands"]["METRICSHUB"]}).json()
    assert client.post(f"/api/opportunities/{o['id']}/quotes", json={}).status_code == 422
    o2 = _opp(client, ref, qty=40)
    q = client.post(f"/api/opportunities/{o2['id']}/quotes", json={}).json()
    assert client.patch(f"/api/quotes/{q['id']}", json={"status": "sent"}).json()["status"] == "sent"
    assert client.delete(f"/api/quotes/{q['id']}").status_code == 409  # only drafts can be deleted


def test_template_edit_validation_and_preview(client, ref):
    brand_id = ref["brands"]["METRICSHUB"]
    tpl = next(t for t in client.get("/api/quote-templates").json() if t["brand_id"] == brand_id)
    body = {k: v for k, v in tpl.items() if k not in ("brand_id", "brand_name")}
    body.update(company_name="ACME Test", intro_text="Hello {customer}, **bold** <script>x</script>",
                accent_color="#123456")
    r = client.put(f"/api/quote-templates/{brand_id}", json=body)
    assert r.status_code == 200 and r.json()["company_name"] == "ACME Test"
    html = client.post("/api/quote-templates/preview", json=body).text
    assert "Hello Example Customer Ltd" in html and "<strong>bold</strong>" in html
    assert "<script>" not in html
    assert client.put(f"/api/quote-templates/{brand_id}", json={**body, "accent_color": "red;}"}).status_code == 422
    assert client.put(f"/api/quote-templates/{brand_id}",
                      json={**body, "logo_data_uri": "https://evil.example/x.png"}).status_code == 422
    pdf = client.post("/api/quote-templates/preview.pdf", json=body)
    assert pdf.content[:4] == b"%PDF"
    reset = client.post(f"/api/quote-templates/{brand_id}/reset").json()
    assert reset["company_name"] == "MetricsHub S.A.S."

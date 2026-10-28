"""Marketing: dynamic audiences, campaigns sent to them, adding contacts to lists, and the overview."""
import datetime as dt
from decimal import Decimal

from app import campaigns
from app.db import SessionLocal
from app.models import Contact, Entitlement

from tests.test_email_marketing import smtp  # noqa: F401 - fake SMTP fixture


def _account(client, name, **extra):
    return client.post("/api/accounts", json={"name": name, "account_type": "customer", **extra}).json()


def _contact(client, first, email, **extra):
    return client.post("/api/contacts", json={"first_name": first, "email": email, **extra}).json()


def _licence(account_id, brand_id, product, end):
    with SessionLocal() as db:
        db.add(Entitlement(account_id=account_id, brand_id=brand_id, product_name=product, quantity=Decimal(10),
                           start_date=dt.date.today() - dt.timedelta(days=400), end_date=end))
        db.commit()


def _zembla(client, ref):
    """Three customers in Zembla: one renewing soon, one renewed long term, one lapsed; and a lead."""
    today = dt.date.today()
    brand = next(iter(ref["brands"].values()))
    soon, later, lapsed = (_account(client, f"Zembla {n}", country="Zembla") for n in ("Soon", "Later", "Lapsed"))
    _licence(soon["id"], brand, "Hardware Sentry", today + dt.timedelta(days=30))
    _licence(later["id"], brand, "Storage Sentry", today + dt.timedelta(days=500))
    _licence(lapsed["id"], brand, "Hardware Sentry", today - dt.timedelta(days=10))
    return {
        "soon": _contact(client, "Sam", "sam@soon.zembla", account_id=soon["id"], lifecycle="customer"),
        "later": _contact(client, "Lea", "lea@later.zembla", account_id=later["id"], lifecycle="customer"),
        "lapsed": _contact(client, "Lou", "lou@lapsed.zembla", account_id=lapsed["id"], lifecycle="customer"),
        "lead": _contact(client, "Liz", "liz@lead.zembla", lifecycle="lead", country="Zembla"),
    }


def _ids(client, rules):
    aud = client.post("/api/audiences", json={"name": f"t {rules}", "rules": rules}).json()
    got = client.get("/api/contacts", params={"audience_id": aud["id"], "page_size": 100}).json()
    return aud, {c["email"] for c in got["items"]}


def test_audience_rules_follow_the_data(client, ref):
    _zembla(client, ref)
    _, everyone = _ids(client, {"country": ["zembla"]})  # a contact's country, or its account's
    assert everyone == {"sam@soon.zembla", "lea@later.zembla", "lou@lapsed.zembla", "liz@lead.zembla"}
    assert _ids(client, {"country": ["Zembla"], "licence": "active"})[1] == {"sam@soon.zembla", "lea@later.zembla"}
    assert _ids(client, {"country": ["Zembla"], "licence": "lapsed"})[1] == {"lou@lapsed.zembla"}
    assert _ids(client, {"country": ["Zembla"], "licence": "none"})[1] == {"liz@lead.zembla"}
    assert _ids(client, {"country": ["Zembla"], "renews_within_days": 90})[1] == {"sam@soon.zembla"}
    assert _ids(client, {"country": ["Zembla"], "product": "storage"})[1] == {"lea@later.zembla"}
    aud, leads = _ids(client, {"country": ["Zembla"], "lifecycle": ["lead"]})
    assert leads == {"liz@lead.zembla"} and aud["counts"] == {"matching": 1, "reachable": 1, "with_consent": 0}

    # a new matching contact joins without anyone touching the audience
    _contact(client, "Max", "max@lead.zembla", lifecycle="lead", country="Zembla")
    assert client.get(f"/api/audiences/{aud['id']}").json()["counts"]["matching"] == 2
    page = client.get(f"/api/audiences/{aud['id']}/contacts").json()
    assert page["total"] == 2 and {i["email"] for i in page["items"]} == {"liz@lead.zembla", "max@lead.zembla"}

    pv = client.post("/api/audiences/preview", json={"country": ["zembla"], "renews_within_days": 90}).json()
    assert pv["matching"] == 1 and pv["sample"][0]["email"] == "sam@soon.zembla"
    assert client.post("/api/audiences/preview", json={"licence": "maybe"}).status_code == 422

    upd = client.put(f"/api/audiences/{aud['id']}", json={"name": "Zembla leads", "rules": {
        "country": ["Zembla"], "lifecycle": ["lead"], "consent_only": True}}).json()
    assert upd["name"] == "Zembla leads" and upd["rules"]["consent_only"] is True and upd["counts"]["matching"] == 0
    assert client.post("/api/audiences", json={"name": "zembla LEADS"}).status_code == 409


def test_campaign_to_an_audience_and_a_list(client, smtp):  # noqa: F811
    """Uses the Zembla contacts made by the test above."""
    renewals = client.post("/api/audiences", json={"name": "Zembla renewals", "rules": {
        "country": ["Zembla"], "renews_within_days": 90}}).json()
    leads = client.post("/api/audiences", json={"name": "Zembla all leads", "rules": {
        "country": ["Zembla"], "lifecycle": ["lead"]}}).json()
    with SessionLocal() as db:
        db.query(Contact).filter(Contact.email == "max@lead.zembla").update({"unsubscribed": True})
        db.commit()
    lst = client.post("/api/lists", json={"name": "Zembla VIPs"}).json()
    sam = client.get("/api/contacts", params={"q": "sam@soon.zembla"}).json()["items"][0]
    client.post(f"/api/lists/{lst['id']}/members", json={"contact_ids": [sam["id"]]})  # also in the audience

    t = client.post("/api/email-templates", json={"name": "Renewal", "subject": "Renew, {first_name}",
                                                  "body_html": "<p>Hi {first_name}</p>"}).json()
    c = client.post("/api/campaigns", json={"name": "Zembla renewals", "template_id": t["id"], "list_ids": [lst["id"]],
                                            "audience_ids": [renewals["id"], leads["id"]]}).json()
    assert c["audience_ids"] == [renewals["id"], leads["id"]]
    summary = client.get(f"/api/campaigns/{c['id']}/audience").json()
    assert summary["recipients"] == 2  # Sam once (list + audience), Liz; Max unsubscribed
    assert summary["skipped_by_reason"] == {"unsubscribed from all marketing email": 1}
    assert client.delete(f"/api/audiences/{leads['id']}").status_code == 409  # a draft campaign uses it

    assert client.post(f"/api/campaigns/{c['id']}/send", json={}).json()["status"] == "sending"
    with SessionLocal() as db:
        campaigns.process(db)
        campaigns.process(db)
    assert sorted(m["To"] for m, _, _ in smtp.sent) == ["liz@lead.zembla", "sam@soon.zembla"]
    assert client.delete(f"/api/audiences/{leads['id']}").status_code == 204  # sent: the report keeps its recipients

    ov = client.get("/api/marketing/overview").json()
    assert ov["email"]["sent"] >= 2 and ov["audiences"] >= 1 and ov["lists"] >= 1
    assert ov["contacts"]["unsubscribed"] >= 1 and any(r["id"] == c["id"] for r in ov["recent"])


def test_add_contacts_to_a_list_and_save_an_audience_as_a_list(client):
    a = _contact(client, "Ann", "ann@bulk.example", lifecycle="lead", country="Ruritania")
    b = _contact(client, "Ben", "ben@bulk.example", lifecycle="lead", country="Ruritania")
    r = client.post("/api/contacts/add-to-list", json={"contact_ids": [a["id"], b["id"]],
                                                       "new_list_name": "Ruritania event"}).json()
    assert r["added"] == 2 and r["list_name"] == "Ruritania event"
    again = client.post("/api/contacts/add-to-list", json={"contact_ids": [a["id"]], "list_id": r["list_id"]}).json()
    assert again == {**r, "added": 0, "already_in_list": 1}
    assert client.post("/api/contacts/add-to-list", json={"contact_ids": [a["id"]],
                                                         "new_list_name": "ruritania EVENT"}).status_code == 409
    assert client.post("/api/contacts/add-to-list", json={"contact_ids": [a["id"]]}).status_code == 422
    in_list = client.get("/api/contacts", params={"list_id": r["list_id"]}).json()
    assert {c["email"] for c in in_list["items"]} == {"ann@bulk.example", "ben@bulk.example"}

    aud = client.post("/api/audiences", json={"name": "Ruritania leads", "rules": {"country": ["Ruritania"]}}).json()
    saved = client.post(f"/api/audiences/{aud['id']}/save-as-list", json={"name": "Ruritania snapshot"}).json()
    assert saved["subscribed"] == 2 and "Ruritania leads" in saved["description"]
    _contact(client, "Cy", "cy@bulk.example", country="Ruritania")
    assert client.get(f"/api/lists/{saved['id']}/members").json()["total"] == 2  # a list does not grow by itself
    assert client.get(f"/api/audiences/{aud['id']}").json()["counts"]["matching"] == 3


def test_import_a_list_from_excel(client):
    """An .xlsx with 'First Name', 'Last Name', 'Company', 'Email' headers (it used to fail with a 500)."""
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["First Name", "Last Name", "Company", "Email"])
    wb.active.append(["Xavier", "Excel", "Spreadsheet Co", "Xavier.Excel@sheets.example"])
    wb.active.append(["No", "Address", "Nowhere", None])
    out = io.BytesIO()
    wb.save(out)
    lst = client.post("/api/lists", json={"name": "From Excel"}).json()
    r = client.post(f"/api/lists/{lst['id']}/import", files={"file": ("TestList.xlsx", out.getvalue())}).json()
    assert r == {"rows": 2, "added": 1, "new_contacts": 1, "invalid_rows": 1}
    c = client.get("/api/contacts", params={"q": "xavier.excel@sheets.example"}).json()["items"][0]
    assert (c["first_name"], c["last_name"]) == ("Xavier", "Excel")

    csv_data = "Prénom;Nom;E-mail\nYves;Point;yves@sheets.example\n"  # French headers, semicolons
    r = client.post(f"/api/lists/{lst['id']}/import", files={"file": ("l.csv", csv_data.encode(), "text/csv")}).json()
    assert r["added"] == 1 and r["new_contacts"] == 1
    bad = client.post(f"/api/lists/{lst['id']}/import", files={"file": ("x.xlsx", b"not a workbook")})
    assert bad.status_code == 422

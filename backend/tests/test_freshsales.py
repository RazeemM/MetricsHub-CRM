"""Freshsales migration: export files through the admin endpoint, and the API client against a fake server."""
import json
from decimal import Decimal

import httpx

ACCOUNTS_CSV = """Id,Name,Website,Phone,Industry type,Country,City,Sales owner
9001,Orion Telecom,https://www.orion-telecom.example/,+33 1 23,Telecommunications,France,Paris,Administrator
9002,Vega Bank,vega-bank.example,,Banking,Germany,Berlin,Ghost Owner
"""
CONTACTS_CSV = """Id,First name,Last name,Emails,Job title,Accounts,Lifecycle stage,Status,Source,Sales owner
7001,Nina,Durand,nina.durand@orion-telecom.example,CIO,Orion Telecom,Sales Qualified Lead,,Web form,Administrator
7002,Karl,Weber,karl.weber@vega-bank.example,IT Ops,Vega Bank,Customer,,BMC referral,admin@example.com
7003,,,,,,Lead,,,
7004,Pat,Partner,pat@datadoghq.com,Account Executive,Datadog,Lead,,,
"""
DEALS_CSV = """Id,Name,Deal value,Currency,Deal stage,Deal pipeline,Expected close date,Account,Sales owner,Source,Contacts,Lost reason,Probability (%)
5001,Orion – MetricsHub 2000 hosts,"360,000.00",USD,Demo,Default pipeline,2026-12-15,Orion Telecom,Administrator,Datadog partner,Nina Durand,,
5002,Vega – Sentry bundle BHOM,250000,EUR,Closed won,Default pipeline,2026-06-30,Vega Bank,Administrator,BMC,karl.weber@vega-bank.example,,
5003,Old lost deal,1000,USD,Closed lost,Default pipeline,2025-01-10,Orion Telecom,,,,Budget cut,
5004,Weird stage deal,500,USD,Waiting on legal,Default pipeline,,New Co From Deal,,,,,40
"""


def _upload(client, commit, **extra):
    files = [("files", ("accounts.csv", ACCOUNTS_CSV.encode(), "text/csv")),
             ("files", ("contacts.csv", CONTACTS_CSV.encode(), "text/csv")),
             ("files", ("deals.csv", DEALS_CSV.encode(), "text/csv"))]
    r = client.post("/api/migrations/freshsales", files=files, data={"commit": str(commit).lower(), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_dry_run_writes_nothing(client):
    rep = _upload(client, False)
    assert rep["dry_run"] is True
    assert rep["counts"]["deals"]["created"] == 4
    assert rep["unmapped_stages"] == {"Waiting on legal": 1}
    assert "Ghost Owner" in rep["unmatched_owners"]
    assert client.get("/api/accounts", params={"q": "Orion Telecom"}).json()["total"] == 0


def test_commit_then_rerun_is_idempotent(client, ref):
    rep = _upload(client, True, stage_map=json.dumps({"Waiting on legal": "Negotiation"}))
    assert rep["counts"]["accounts"]["created"] == 2
    assert rep["counts"]["contacts"]["created"] == 3 and rep["counts"]["contacts"]["skipped (no name or email)"] == 1
    assert rep["counts"]["deals"]["created"] == 4
    assert rep["stage_mapping"]["Closed won"] == "Won" and rep["stage_mapping"]["Waiting on legal"] == "Negotiation"

    orion = client.get("/api/accounts", params={"q": "Orion Telecom"}).json()["items"][0]
    assert orion["domain"] == "orion-telecom.example" and orion["owner"]["full_name"] == "Administrator"
    nina = client.get("/api/contacts", params={"q": "nina.durand"}).json()["items"][0]
    assert nina["lifecycle"] == "qualified" and nina["source"] == "website_contact" and nina["account"]["id"] == orion["id"]
    pat = client.get("/api/contacts", params={"q": "pat@datadoghq.com"}).json()["items"][0]
    assert pat["role"] == "platform_account_manager"

    deals = {o["title"]: o for o in client.get("/api/opportunities", params={"page_size": 500}).json()["items"]}
    d1 = deals["Orion – MetricsHub 2000 hosts"]
    assert Decimal(d1["amount_tcv"]) == Decimal("360000.00") and d1["stage"]["name"] == "Demo"
    assert d1["referring_platform"]["name"] == "Datadog" and d1["primary_contact"]["id"] == nina["id"]
    d2 = deals["Vega – Sentry bundle BHOM"]
    assert d2["brand"]["name"] == "Sentry Software" and d2["currency"] == "EUR" and d2["stage"]["kind"] == "won"
    assert d2["route_to_market"] == "bmc_marketzone"
    assert client.get(f"/api/accounts/{d2['account']['id']}").json()["account_type"] == "customer"
    assert deals["Old lost deal"]["lost_reason"] == "Budget cut"
    assert deals["Weird stage deal"]["account"]["name"] == "New Co From Deal"

    again = _upload(client, True, stage_map=json.dumps({"Waiting on legal": "Negotiation"}))
    assert again["counts"]["deals"] == {"updated": 4}
    assert again["counts"]["accounts"] == {"updated": 2}
    titles = [o["title"] for o in client.get("/api/opportunities", params={"page_size": 500}).json()["items"]]
    assert titles.count("Orion – MetricsHub 2000 hosts") == 1


def test_only_admins_can_migrate(client):
    from fastapi.testclient import TestClient

    from app.main import app
    client.post("/api/users", json={"email": "rep2@example.com", "full_name": "Rep Two", "role": "sales",
                                    "password": "salesrep123"})
    with TestClient(app) as c:
        t = c.post("/api/auth/login", data={"username": "rep2@example.com", "password": "salesrep123"}).json()
        c.headers["Authorization"] = f"Bearer {t['access_token']}"
        r = c.post("/api/migrations/freshsales", files=[("files", ("deals.csv", DEALS_CSV.encode(), "text/csv"))])
        assert r.status_code == 403


def test_api_client_against_fake_freshsales(client):
    from app.db import SessionLocal
    from app.migration.freshsales import FreshsalesClient, from_api, load

    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.headers["Authorization"] == "Token token=test-key"
        p, q = req.url.path.removeprefix("/crm/sales/api/"), dict(req.url.params)
        sel = {"selector/owners": {"users": [{"id": 1, "email": "admin@example.com"}]},
               "selector/deal_stages": {"deal_stages": [{"id": 11, "name": "Negotiation"}]},
               "selector/deal_pipelines": {"deal_pipelines": [{"id": 21, "name": "Default"}]},
               "selector/deal_pipelines/21/deal_stages": {"deal_stages": [{"id": 11, "name": "Negotiation"}]},
               "selector/currencies": {"currencies": [{"id": 31, "currency_code": "EUR"}]},
               "selector/lead_sources": {"lead_sources": [{"id": 41, "name": "Web Form"}]},
               "selector/lifecycle_stages": {"lifecycle_stages": [{"id": 51, "name": "Customer"}]},
               "selector/industry_types": {"industry_types": [{"id": 61, "name": "Energy"}]},
               "selector/deal_reasons": {"deal_reasons": []}, "selector/deal_types": {"deal_types": []}}
        if p in sel:
            return httpx.Response(200, json=sel[p])
        if p.endswith("/filters"):
            return httpx.Response(200, json={"filters": [{"id": 99, "name": "All items"}]})
        page = int(q.get("page", 1))
        if p == "sales_accounts/view/99":
            items = [{"id": 801 + i + (page - 1) * 2, "name": f"API Account {page}-{i}", "industry_type_id": 61,
                      "owner_id": 1, "website": f"api{page}{i}.example"} for i in range(2)]
            return httpx.Response(200, json={"sales_accounts": items, "meta": {"total_pages": 2}})
        if p == "contacts/view/99":
            assert q.get("include") == "sales_accounts"
            return httpx.Response(200, json={"contacts": [{"id": 701, "first_name": "Api", "last_name": "Person",
                "email": "api.person@api11.example", "lifecycle_stage_id": 51, "lead_source_id": 41,
                "sales_accounts": [{"id": 801, "name": "API Account 1-0", "is_primary": True}]}], "meta": {"total_pages": 1}})
        if p == "deals/view/99":
            return httpx.Response(200, json={"deals": [{"id": 601, "name": "API deal", "amount": "12000.5",
                "currency_id": 31, "deal_stage_id": 11, "deal_pipeline_id": 21, "sales_account_id": 801,
                "owner_id": 1, "contact_ids": [701], "expected_close": "2026-11-30"}], "meta": {"total": 1}})
        return httpx.Response(404, json={})

    fc = FreshsalesClient("acme", "test-key")
    assert fc.base == "https://acme.myfreshworks.com/crm/sales/api"
    fc.http = httpx.Client(transport=httpx.MockTransport(handler), headers=fc.http.headers)
    ds = from_api(fc, log=lambda *_: None)
    assert len(ds.accounts) == 4 and len(ds.contacts) == 1 and len(ds.deals) == 1
    with SessionLocal() as db:
        rep = load(db, ds, dry_run=False)
    assert rep.counts["deals"]["created"] == 1 and not rep.unmapped_stages
    deal = client.get("/api/opportunities", params={"q": "API deal"}).json()["items"][0]
    assert deal["stage"]["name"] == "Negotiation" and deal["currency"] == "EUR"
    assert Decimal(deal["amount_tcv"]) == Decimal("12000.50") and deal["primary_contact"]["email"] == "api.person@api11.example"
    assert all(req.method == "GET" for req in calls)  # read-only

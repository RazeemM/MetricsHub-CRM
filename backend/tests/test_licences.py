"""Licences from BMC MarketZone reports: parsing, import, holdings, renewal notices, lapses and search.

Uses invented customers only: real reports are confidential and must not be committed."""
import datetime as dt
from decimal import Decimal

from app import entitlements as ent
from app import mzd_report
from app.db import SessionLocal
from app.models import Entitlement, Notification
from app.mzd_report import Report, ReportLine

TODAY = dt.date.today()


def _w(x0, text, top=200.0):
    return {"x0": x0, "x1": x0 + 4.2 * len(text), "top": top, "bottom": top + 7, "text": text}


def test_parse_line_splits_columns_by_gaps():
    words = []
    for x, cell in [(107, "INV00012345"), (181, "5/25/26"), (239, "Acme Widgets B.V. & Co. KG"), (461, "Germany"),
                    (574, "Partner Reseller GmbH"), (786, "Sentry Hardware Analyzer for TrueSight Operations Management"),
                    (1121, "Term"), (1192, "4/1/2026"), (1244, "3/31/2027"), (1306, "365"), (1393, "8,777"),
                    (1424, "200,223.94"), (1482, "102,114.21")]:
        for i, t in enumerate(cell.split()):  # words of one cell are close together
            words.append(_w(x + sum(4.2 * len(p) + 4 for p in cell.split()[:i]), t))
    line = mzd_report.parse_line(mzd_report._cells(words), 2)
    assert line.customer == "Acme Widgets B.V. & Co. KG" and line.billing_company == "Partner Reseller GmbH"
    assert line.product == "Sentry Hardware Analyzer for TrueSight Operations Management"
    assert line.license_type == "term" and line.start == dt.date(2026, 4, 1) and line.end == dt.date(2027, 3, 31)
    assert line.quantity == Decimal("8777") and line.net == Decimal("200223.94")


def test_rejects_other_pdfs():
    try:
        mzd_report.parse(b"not a pdf")
    except mzd_report.ReportError as exc:
        assert "PDF" in str(exc)
    else:
        raise AssertionError("expected ReportError")


def _line(doc, customer, product, qty, start, end, billing=None, kind="term", net="100.00"):
    return ReportLine(doc_number=doc, doc_date=TODAY, customer=customer, country="Freedonia",
                      billing_company=billing or customer, product=product, license_type=kind, start=start, end=end,
                      term_days=(end - start).days, quantity=Decimal(qty), net=Decimal(net), fee=Decimal("1"), page=2)


def _report():
    y = dt.timedelta(days=365)
    return Report(title="Reseller Fee Report to Sentry Software", warnings=[], lines=[
        # renewal in 30 days -> due
        _line("INV1", "Zorblax Freight Corporation", "Sentry Monitoring Studio", "50", TODAY - y + dt.timedelta(days=30),
              TODAY + dt.timedelta(days=30), billing="Initech Reseller Ltd"),
        _line("INV1", "Zorblax Freight Corporation", "Sentry Monitoring Studio", "25", TODAY - y + dt.timedelta(days=30),
              TODAY + dt.timedelta(days=30), billing="Initech Reseller Ltd"),
        # ended 10 days ago -> lapsed
        _line("INV2", "Zorblax Freight Corporation", "Sentry Storage Analyzer", "10", TODAY - y, TODAY - dt.timedelta(days=10),
              kind="support"),
        # prepaid for two more years -> active, renewal at the end of the last paid year
        _line("INV3", "Quuxly Holdings", "Sentry Bundle - Resource Unit", "400", TODAY - dt.timedelta(days=100),
              TODAY + dt.timedelta(days=265), kind="saas"),
        _line("INV3", "Quuxly Holdings", "Sentry Bundle - Resource Unit", "400", TODAY + dt.timedelta(days=265),
              TODAY + dt.timedelta(days=630), kind="saas"),
        # invoiced then fully credited -> cancelled, never lapsed
        _line("INV4", "Quuxly Holdings", "Sentry Hardware Monitor", "5", TODAY - y, TODAY - dt.timedelta(days=5)),
        _line("CM9", "Quuxly Holdings", "Sentry Hardware Monitor", "-5", TODAY - y, TODAY - dt.timedelta(days=5),
              net="-100.00"),
    ])


def test_import_is_idempotent_and_builds_holdings(client):
    with SessionLocal() as db:
        dry = ent.import_report(db, _report(), "q2.pdf", dry_run=True)
        assert dry.created == 7 and "Zorblax Freight Corporation" in dry.accounts_created
        assert dry.resellers == {"Initech Reseller Ltd": "Initech Reseller Ltd (new)"}
    with SessionLocal() as db:
        assert db.query(Entitlement).count() == 0
        res = ent.import_report(db, _report(), "q2.pdf", dry_run=False)
        assert res.created == 7
    with SessionLocal() as db:
        again = ent.import_report(db, _report(), "q2.pdf", dry_run=False)
        assert again.created == 0 and again.already_imported == 7

    globex = client.get("/api/accounts", params={"q": "Zorblax"}).json()["items"][0]
    assert globex["account_type"] == "customer"
    lic = client.get(f"/api/accounts/{globex['id']}/licences").json()
    h = {x["product_name"]: x for x in lic["holdings"]}
    studio = h["Sentry Monitoring Studio"]
    assert Decimal(studio["quantity"]) == 75 and studio["status"] == "renewal_due"
    assert studio["reseller"] == "Initech Reseller Ltd" and studio["days_to_renewal"] == 30
    assert h["Sentry Storage Analyzer"]["status"] == "lapsed"

    umbrella = client.get("/api/accounts", params={"q": "Quuxly"}).json()["items"][0]
    h = {x["product_name"]: x for x in client.get(f"/api/accounts/{umbrella['id']}/licences").json()["holdings"]}
    bundle = h["Sentry Bundle - Resource Unit"]
    assert bundle["status"] == "active" and Decimal(bundle["quantity"]) == 400
    assert bundle["renewal_date"] == (TODAY + dt.timedelta(days=630)).isoformat()
    assert h["Sentry Hardware Monitor"]["status"] == "cancelled"


def test_search_lists_products_and_renewals(client):
    acc = client.get("/api/search", params={"q": "Zorblax"}).json()["accounts"][0]
    lic = acc["licences"]
    assert {p["product"] for p in lic["products"]} == {"Sentry Monitoring Studio", "Sentry Storage Analyzer"}
    assert lic["lapsed"] == 1 and lic["next_renewal"] == (TODAY + dt.timedelta(days=30)).isoformat()


def test_lapsed_stays_on_dashboard_until_resolved(client):
    lapsed = client.get("/api/licences/lapsed").json()
    assert [x["product_name"] for x in lapsed] == ["Sentry Storage Analyzer"]
    line = lapsed[0]["latest_line_id"]
    assert client.post(f"/api/licences/{line}/resolve", json={"note": ""}).status_code == 422
    r = client.post(f"/api/licences/{line}/resolve", json={"note": "Customer moved to BHOM SaaS"})
    assert r.status_code == 200 and r.json()["resolved"] and r.json()["resolved_by"] == "Administrator"
    assert client.get("/api/licences/lapsed").json() == []
    assert len(client.get("/api/licences/lapsed", params={"include_resolved": True}).json()) == 1
    client.post(f"/api/licences/{line}/reopen")
    assert len(client.get("/api/licences/lapsed").json()) == 1


def test_renewal_notice_once_to_account_owner(client):
    with SessionLocal() as db:
        assert ent.send_renewal_notices(db) == 1  # Zorblax: Monitoring Studio due in 30 days
        assert ent.send_renewal_notices(db) == 0  # never twice for the same renewal
        n = db.query(Notification).one()
        assert n.kind == "renewal_due" and "Zorblax" in n.title and "Sentry Monitoring Studio: 75" in n.body
    inbox = client.get("/api/notifications").json()
    assert inbox["unread"] == 1 and inbox["items"][0]["link"].startswith("/accounts/")
    assert client.post("/api/notifications/read").status_code == 204
    assert client.get("/api/notifications").json()["unread"] == 0


def test_notice_window_respects_setting(monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "renewal_notice_days", 10)
    with SessionLocal() as db:
        statuses = {h.product_name: h.status for h in ent.holdings(db)}
    assert statuses["Sentry Monitoring Studio"] == "active"


def test_manual_licence_and_admin_delete(client):
    acc = client.post("/api/accounts", json={"name": "Hooli Direct"}).json()
    r = client.post(f"/api/accounts/{acc['id']}/licences", json={
        "product_name": "Sentry Storage Monitor", "quantity": 12, "license_type": "saas",
        "end_date": (TODAY + dt.timedelta(days=200)).isoformat()})
    assert r.status_code == 201
    assert client.delete(f"/api/licences/{r.json()['id']}").status_code == 204
    assert client.get(f"/api/accounts/{acc['id']}/licences").json()["holdings"] == []


def test_upload_endpoint_rejects_non_reports(client):
    r = client.post("/api/licences/import/bmc-mzd", files={"file": ("x.pdf", b"%PDF-1.4 nothing", "application/pdf")})
    assert r.status_code == 422


def _ent(qty, start, end, source="bmc_mzd"):
    from types import SimpleNamespace
    return SimpleNamespace(id=1, account_id=1, account=SimpleNamespace(name="X"), product_name="P", product_id=None,
                           license_type="saas", quantity=Decimal(qty), start_date=start, end_date=end, source=source,
                           reseller=None, lapse_resolved_at=None, lapse_resolution=None, lapse_resolved_by=None)


def test_quarterly_instalments_wait_for_the_next_report():
    d = dt.date
    quarter = [_ent("50", d(2026, 6, 3), d(2026, 9, 2))]
    # report invoices only reach 30 June: the September instalment can't be in it yet
    h = ent._holding(quarter, d(2026, 10, 15), 60, report_cutoff=d(2026, 6, 30))
    assert h.status == "awaiting_report" and h.installments
    # once a report covering September is imported without a new instalment, it has lapsed
    assert ent._holding(quarter, d(2026, 10, 15), 60, report_cutoff=d(2026, 9, 30)).status == "lapsed"
    # instalments never trigger the 2-month renewal notice
    assert ent._holding(quarter, d(2026, 8, 1), 60, report_cutoff=d(2026, 6, 30)).status == "active"
    # a licence added by hand lapses on its end date
    manual = [_ent("5", d(2025, 9, 1), d(2026, 8, 31), source="manual")]
    assert ent._holding(manual, d(2026, 10, 15), 60, report_cutoff=None).status == "lapsed"

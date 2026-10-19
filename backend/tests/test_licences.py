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


def _xlsx(rows) -> bytes:
    import io

    from openpyxl import Workbook
    wb = Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


NEW_HEADER = ["Inv Cm Number", "Inv Cm Date", "Ordering Company (Subscription Owner)", "Sold To Country",
              "Billing Company (Invoice Owner)", "Product Name", "Product Rate Plan Charge Revenue Type",
              "Inv Service Start Date", "Inv Service End Date", "Maintenance term (days)", "INV CM Quantity Metric",
              "Total Net", "Fee"]


def test_detail_xlsx_with_totals_credits_and_perpetual():
    data = _xlsx([
        NEW_HEADER,
        ["INV00012345", dt.datetime(2026, 5, 25), "Acme Widgets B.V. & Co. KG", "Germany", "Partner Reseller GmbH",
         "Sentry Hardware Analyzer for TrueSight Operations Management", "Term", "4/1/2026", "3/31/2027", 365, 3,
         2874.8, 1466.15],
        ["CM00000001", dt.datetime(2026, 6, 10), "Acme Widgets B.V. & Co. KG", "Germany", "Partner Reseller GmbH",
         "Sentry Hardware Analyzer for TrueSight Operations Management", "Term", "4/1/2026", "3/31/2027", 365, -1,
         -958.27, -488.72],
        [None] * 9 + ["Term Total:", 2, 1916.53, 977.43],
        ["204311018", dt.datetime(2025, 12, 24), "Credit Agricole Freedonia", "Freedonia", "Credit Agricole Freedonia",
         "Sentry for TrueSight Operations Management", "License", "11/8/2024", "11/8/2024", 1, 1, 129.67, 51.87],
        [None] * 8 + ["Resource Bundle License:", None, 1, 129.67, 51.87],  # a subtotal without the word "Total"
    ])
    rep = mzd_report.parse(data, "Detail.xlsx")
    assert rep.source == "xlsx" and rep.reliable and rep.checked_totals == 2
    first, credit, lic = rep.lines
    assert first.customer == "Acme Widgets B.V. & Co. KG" and first.billing_company == "Partner Reseller GmbH"
    assert first.start == dt.date(2026, 4, 1) and first.end == dt.date(2027, 3, 31) and first.quantity == 3
    assert credit.quantity == -1 and credit.net == Decimal("-958.27")
    assert lic.license_type == "perpetual" and lic.customer == "Credit Agricole Freedonia"  # "Credit" is a real name


def test_totals_that_do_not_add_up_make_the_report_unreliable():
    data = _xlsx([NEW_HEADER,
                  ["INV1", dt.datetime(2026, 5, 25), "Acme", "Freedonia", "Acme", "Sentry X", "Term", "4/1/2026",
                   "3/31/2027", 365, 3, 100, 50],
                  [None] * 9 + ["Term Total:", 5, 100, 50]])
    rep = mzd_report.parse(data, "Detail.xlsx")
    assert not rep.reliable and "Term Total" in rep.warnings[0]


def test_old_layout_headers_are_recognised():
    old = ["Revenue Type", "Product Name", "Invoice #", "Invoice Date", "Invoice Type", "Install Company",
           "Install Country", "Billing Company", "Ref Inv #", "Number of copies", "US Converted Net Amount", "Fee",
           "Maintenance Begin Date", "Maintenance End Date", "Maintenance Term(Days)"]
    assert [mzd_report.field_for(h) for h in old] == [
        "charge", "product", "doc", "doc_date", "doc_type", "customer", "country", "billing", "overflow", "qty", "net",
        "fee", "start", "end", "days"]
    assert mzd_report.field_for("Oracle Ar Inv Cm Number") == "doc"


def test_pdf_totals_with_spaced_digits():
    assert mzd_report.total_numbers("Term Total: 5,483 1 52,568.79 8 3,912.83") == (Decimal(5483), Decimal("152568.79"))
    assert mzd_report.total_numbers("Converged Term total: 6 691.46 152.12") == (Decimal(6), Decimal("691.46"))
    assert mzd_report.total_numbers("Bundle prior to April 2026Total: (2,770) (2,661.25) (1,304.01)") == (
        Decimal(-2770), Decimal("-2661.25"))
    assert mzd_report.total_numbers("Total Payment Due $ 364,025.79") is None


def test_cells_that_ran_together_are_split_by_content():
    def ws(text):
        return [{"text": t, "x0": i * 30.0, "x1": i * 30.0 + 25} for i, t in enumerate(text.split())]
    s = mzd_report._split_cell
    assert s(ws("PERPETUAL Rev Sentry Monitoring Studio"), ["charge", "product"]) == {
        "charge": "PERPETUAL Rev", "product": "Sentry Monitoring Studio"}
    assert s(ws("23871693/20/2020"), ["doc", "doc_date"]) == {"doc_date": "3/20/2020", "doc": "2387169"}
    assert s(ws("InvoiceAcme Widgets Ltd"), ["doc_type", "customer"]) == {"doc_type": "Invoice",
                                                                         "customer": "Acme Widgets Ltd"}
    assert s(ws("1,559.76 8/6/2024 8/5/2027"), ["fee", "start", "end"]) == {
        "fee": "1,559.76", "start": "8/6/2024", "end": "8/5/2027"}


def test_glued_columns_are_rejected_not_imported():
    base = {"doc": "INV1", "product": "Sentry X", "charge": "Term", "qty": 1, "net": 1, "end": "1/1/2027",
            "billing": "Acme"}
    for bad in ("RENEWAL SUPPORTACME INTERNATIONAL", "Invoice Acme Ltd", "ADD Acme Ltd"):
        try:
            mzd_report.make_line({**base, "customer": bad}, 1)
        except mzd_report.ReportError as exc:
            assert "another column" in str(exc)
        else:
            raise AssertionError(bad)
    try:
        mzd_report.make_line({**base, "customer": "Acme Disclosure Statement " + "x" * 300}, 1)
    except mzd_report.ReportError as exc:
        assert "not read correctly" in str(exc)


def test_rejects_other_files():
    for data, name in ((b"not a report", "x.txt"), (b"%PDF-1.4 nothing", "x.pdf")):
        try:
            mzd_report.parse(data, name)
        except mzd_report.ReportError:
            pass
        else:
            raise AssertionError(name)


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


def _ent(qty, start, end, source="bmc_mzd", kind="saas"):
    from types import SimpleNamespace
    return SimpleNamespace(id=1, account_id=1, account=SimpleNamespace(name="X"), product_name="P",
                           license_type=kind, quantity=Decimal(qty), start_date=start, end_date=end, source=source,
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


def test_perpetual_licences_never_lapse_or_renew():
    d = dt.date
    lic = [_ent("200", d(2020, 3, 20), None, kind="perpetual"), _ent("50", d(2024, 2, 1), None, kind="perpetual")]
    h = ent._holding(lic, d(2026, 10, 15), 60, report_cutoff=d(2026, 6, 30))
    assert h.status == "perpetual" and h.quantity == 250 and h.renewal_date is None and h.days_to_renewal is None


def test_manual_perpetual_licence_needs_no_end_date(client):
    acc = client.post("/api/accounts", json={"name": "Perpetua Direct"}).json()
    r = client.post(f"/api/accounts/{acc['id']}/licences", json={"product_name": "Sentry Storage Analyzer",
                                                                  "quantity": 40, "license_type": "perpetual"})
    assert r.status_code == 201
    assert client.post(f"/api/accounts/{acc['id']}/licences", json={
        "product_name": "X", "quantity": 1, "license_type": "term"}).status_code == 422
    h = client.get(f"/api/accounts/{acc['id']}/licences").json()["holdings"][0]
    assert h["status"] == "perpetual" and h["renewal_date"] is None


def test_unreliable_report_cannot_be_imported(client):
    data = _xlsx([NEW_HEADER,
                  ["INV9", dt.datetime(2026, 5, 25), "Wrongsum Ltd", "Freedonia", "Wrongsum Ltd", "Sentry X", "Term",
                   "4/1/2026", "3/31/2027", 365, 3, 100, 50],
                  [None] * 9 + ["Term Total:", 5, 100, 50]])
    files = {"file": ("Detail.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    dry = client.post("/api/licences/import/bmc-mzd", files=files, data={"commit": "false"})
    assert dry.status_code == 200 and dry.json()["reliable"] is False and dry.json()["warnings"]
    r = client.post("/api/licences/import/bmc-mzd", files=files, data={"commit": "true"})
    assert r.status_code == 422 and "Not imported" in r.json()["detail"]
    assert client.get("/api/accounts", params={"q": "Wrongsum"}).json()["total"] == 0


def test_dashboard_licence_analytics_and_fee_backfill(client):
    y = TODAY.year
    d = dt.date

    def ln(doc, customer, country, product, qty, start, end, net, fee):
        return ReportLine(doc_number=doc, doc_date=start, customer=customer, country=country, billing_company=customer,
                          product=product, license_type="term", start=start, end=end, term_days=365,
                          quantity=Decimal(qty), net=Decimal(net), fee=Decimal(fee), page=2)
    lines = [
        ln("AN1", "Analytica Iberia SA", "Spain", "Probe Monitor", "10", d(y, 1, 15), d(y + 1, 1, 14), "1000.00", "510.00"),
        ln("AN2", "Analytica Gulf LLC", "Saudi Arabia", "Probe Monitor", "5", d(y - 1, 3, 1), d(y, 2, 28), "600.00",
           "306.00"),
        ln("AN3", "Analytica Pacific Pty", "Australia", "Probe Analyzer", "2", d(y - 2, 6, 1), d(y - 1, 5, 31), "400.00",
           "204.00"),
    ]
    with SessionLocal() as db:
        ent.import_report(db, Report(title="t", lines=lines, warnings=[]), "analytics.xlsx", dry_run=False)
        # simulate lines imported before fees were stored, then a re-import fills them
        db.query(Entitlement).filter(Entitlement.source_ref.in_(["AN1", "AN2", "AN3"])).update({"fee_amount": None})
        db.commit()
    a = client.get("/api/dashboard/licences").json()
    assert a["lines_missing_fee"] >= 3
    with SessionLocal() as db:
        res = ent.import_report(db, Report(title="t", lines=lines, warnings=[]), "analytics.xlsx", dry_run=False)
        assert res.fees_filled == 3 and res.created == 0

    a = client.get("/api/dashboard/licences", params={"period": str(y)}).json()
    prods = {p["product"]: p for p in a["products"]}
    assert prods["Probe Monitor"]["customers"] == 1  # the Saudi licence ended in February: no longer held
    assert Decimal(prods["Probe Monitor"]["revenue"]) == Decimal("1000.00")  # only this year's invoice
    regions = {r["name"]: Decimal(r["amount"]) for r in a["revenue_by_region"]}
    assert regions["Europe"] >= Decimal("1000.00") and "Asia Pacific" not in regions  # its invoice is from y-2
    countries = {r["name"] for r in a["revenue_by_country"]}
    assert "Spain" in countries and "Australia" not in countries

    years = {row["year"]: row for row in a["active_customers"]}
    assert set(years) == {y - 2, y - 1, y}
    assert years[y]["Europe"] >= 1 and years[y]["Middle East & Africa"] >= 1  # Gulf licence ran into this year
    assert years[y - 2]["Asia Pacific"] >= 1
    money = {row["year"]: row for row in a["invoiced_vs_fee"]}
    assert [r["year"] for r in a["invoiced_vs_fee"]] == [y - 3, y - 2, y - 1, y]
    assert Decimal(money[y]["fee"]) >= Decimal("510.00") and Decimal(money[y - 1]["invoiced"]) >= Decimal("600.00")
    assert a["regions"] == ["Americas", "Europe", "Middle East & Africa", "Asia Pacific", "Other"]


def test_region_mapping():
    from app.regions import region_of
    assert region_of("USA") == "Americas" and region_of("Taiwan, Republic of China") == "Asia Pacific"
    assert region_of("Saudi Arabia") == "Middle East & Africa" and region_of("Spain") == "Europe"
    assert region_of("Atlantis") == "Other" and region_of(None) == "Other"
    assert region_of("India", "Middle East & Africa") == "Middle East & Africa"  # the account's own region wins


def test_impossible_fee_is_left_out_and_listed(client):
    y = TODAY.year
    bad = ReportLine(doc_number="BADFEE1", doc_date=dt.date(y, 2, 1), customer="Feecheck Corp", country="India",
                     billing_company="Feecheck Corp", product="Probe Bundle", license_type="saas",
                     start=dt.date(y, 2, 1), end=dt.date(y + 1, 1, 31), term_days=365, quantity=Decimal("628"),
                     net=Decimal("11212.83"), fee=Decimal("7041657.24"), page=2)
    before = {r["year"]: Decimal(r["fee"]) for r in client.get("/api/dashboard/licences").json()["invoiced_vs_fee"]}
    with SessionLocal() as db:
        ent.import_report(db, Report(title="t", lines=[bad], warnings=[]), "Sept.xlsx", dry_run=False)
    a = client.get("/api/dashboard/licences").json()
    assert {r["year"]: Decimal(r["fee"]) for r in a["invoiced_vs_fee"]}[y] == before[y]
    assert any(x["invoice"] == "BADFEE1" and x["report"] == "Sept.xlsx" for x in a["fees_excluded"])


def test_dry_run_reports_fees_to_fill_without_saving_them():
    line = ReportLine(doc_number="FEEDRY1", doc_date=TODAY, customer="Feedry Ltd", country="Spain",
                      billing_company="Feedry Ltd", product="Probe Backup", license_type="term", start=TODAY,
                      end=TODAY + dt.timedelta(days=365), term_days=365, quantity=Decimal("1"), net=Decimal("100.00"),
                      fee=Decimal("51.00"), page=2)
    rep = Report(title="t", lines=[line], warnings=[])
    with SessionLocal() as db:
        ent.import_report(db, rep, "feedry.xlsx", dry_run=False)
        db.query(Entitlement).filter(Entitlement.source_ref == "FEEDRY1").update({"fee_amount": None})
        db.commit()
    with SessionLocal() as db:
        dry = ent.import_report(db, rep, "feedry.xlsx", dry_run=True)
        assert dry.fees_filled == 1 and dry.created == 0
    with SessionLocal() as db:
        assert db.query(Entitlement).filter(Entitlement.source_ref == "FEEDRY1").one().fee_amount is None
        assert ent.import_report(db, rep, "feedry.xlsx", dry_run=False).fees_filled == 1
    with SessionLocal() as db:
        assert db.query(Entitlement).filter(Entitlement.source_ref == "FEEDRY1").one().fee_amount == Decimal("51.00")


def test_sold_to_country_of_the_report_wins_over_the_account(client):
    """A customer matched to an existing account keeps the report's Sold To Country on its lines."""
    acc = client.post("/api/accounts", json={"name": "Countrycheck Holdings"}).json()  # no country
    y = TODAY.year
    line = ReportLine(doc_number="CTRY1", doc_date=dt.date(y, 3, 1), customer="Countrycheck Holdings",
                      country="Saudi Arabia", billing_company="Countrycheck Holdings", product="Probe Storage",
                      license_type="term", start=dt.date(y, 3, 1), end=dt.date(y + 1, 2, 28), term_days=365,
                      quantity=Decimal("3"), net=Decimal("700.00"), fee=Decimal("357.00"), page=2)
    rep = Report(title="t", lines=[line], warnings=[])
    with SessionLocal() as db:
        ent.import_report(db, rep, "ctry.xlsx", dry_run=False)
        e = db.query(Entitlement).filter(Entitlement.source_ref == "CTRY1").one()
        assert e.country == "Saudi Arabia" and e.account_id == acc["id"]
    assert client.get(f"/api/accounts/{acc['id']}").json()["country"] == "Saudi Arabia"  # empty account filled

    # the account says something else: the line's country still decides the charts
    client.patch(f"/api/accounts/{acc['id']}", json={"country": "France"})
    a = client.get("/api/dashboard/licences", params={"period": str(y)}).json()
    countries = {r["name"] for r in a["revenue_by_country"]}
    assert "Saudi Arabia" in countries
    with SessionLocal() as db:
        from app import insights
        ln = next(x for x in insights.load(db) if x.e.source_ref == "CTRY1")
        assert ln.region == "Middle East & Africa"

    # lines imported before the country was stored get it from a re-import
    with SessionLocal() as db:
        db.query(Entitlement).filter(Entitlement.source_ref == "CTRY1").update({"country": None})
        db.commit()
        dry = ent.import_report(db, rep, "ctry.xlsx", dry_run=True)
        assert dry.countries_filled == 1 and dry.created == 0
    with SessionLocal() as db:
        assert ent.import_report(db, rep, "ctry.xlsx", dry_run=False).countries_filled == 1
        assert db.query(Entitlement).filter(Entitlement.source_ref == "CTRY1").one().country == "Saudi Arabia"

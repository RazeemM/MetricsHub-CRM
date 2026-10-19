"""Insights: renewals at risk, retention, reseller scorecard, credit memos, whitespace (invented data)."""
import datetime as dt
from decimal import Decimal

from app import entitlements as ent
from app import insights
from app.db import SessionLocal
from app.mzd_report import Report, ReportLine

T = dt.date.today()
Y = T.year


def _ln(doc, customer, product, qty, start, end, net, billing=None, country="Freedonia", kind="term"):
    return ReportLine(doc_number=doc, doc_date=start, customer=customer, country=country,
                      billing_company=billing or customer, product=product, license_type=kind, start=start, end=end,
                      term_days=(end - start).days, quantity=Decimal(qty), net=Decimal(net), fee=Decimal(net) / 2,
                      page=2)


def _load(lines):
    with SessionLocal() as db:
        ent.import_report(db, Report(title="t", lines=lines, warnings=[]), "insights.xlsx", dry_run=False)


def test_per_year_spreads_a_multi_year_licence():
    from types import SimpleNamespace
    e = SimpleNamespace(net_amount=Decimal("3000"), start_date=dt.date(2024, 1, 1), end_date=dt.date(2026, 12, 31),
                        document_date=dt.date(2024, 1, 1))
    split = insights.per_year(e)
    assert set(split) == {2024, 2025, 2026} and abs(sum(split.values()) - Decimal("3000")) < Decimal("0.01")
    assert abs(split[2025] - Decimal("999.09")) < 1  # 365 of 1096 days


def test_insights_end_to_end(client):
    soon = T + dt.timedelta(days=40)
    _load([
        # renewal soon, annual value 12,000, via a reseller
        _ln("IN1", "Insight Alpha Ltd", "Sentry Hardware Monitor", "100", soon - dt.timedelta(days=364), soon,
            "12000.00", billing="Insight Reseller GmbH"),
        # previous year 1,000 -> this year 2,000: expanded
        _ln("IN2", "Insight Beta SA", "Sentry Storage Monitor", "10", dt.date(Y - 1, 1, 1), dt.date(Y - 1, 12, 31),
            "1000.00"),
        _ln("IN3", "Insight Beta SA", "Sentry Storage Monitor", "20", dt.date(Y, 1, 1), dt.date(Y, 12, 31), "2000.00"),
        _ln("IN3", "Insight Beta SA", "Sentry Hardware Monitor", "20", dt.date(Y, 1, 1), dt.date(Y, 12, 31), "0.00"),
        # previous year only: churned
        _ln("IN4", "Insight Gamma AG", "Sentry Storage Analyzer", "5", dt.date(Y - 1, 1, 1), dt.date(Y - 1, 12, 31),
            "500.00"),
        # credited twice and re-invoiced
        _ln("CM1", "Insight Delta Co", "Sentry Backup Monitor", "-2", dt.date(Y, 1, 1), dt.date(Y, 12, 31), "-80.00"),
        _ln("CM2", "Insight Delta Co", "Sentry Backup Monitor", "-2", dt.date(Y, 1, 2), dt.date(Y, 12, 31), "-80.00"),
        _ln("IN5", "Insight Delta Co", "Sentry Backup Monitor", "2", dt.date(Y, 1, 3), dt.date(Y + 1, 1, 2), "80.00"),
        # whitespace: Storage owners usually also have Hardware
        *[_ln(f"WS{i}", f"Insight Pair {i}", p, "1", dt.date(Y, 1, 1), dt.date(Y + 1, 12, 31), "10.00")
          for i in range(4) for p in ("Sentry Storage Monitor OnPrem", "Sentry Hardware Monitor OnPrem")],
        _ln("WS9", "Insight Lonely Storage", "Sentry Storage Analyzer for TrueSight", "1", dt.date(Y, 1, 1),
            dt.date(Y + 1, 12, 31), "10.00"),
    ])

    r = {x["account"]: x for x in client.get("/api/insights/renewals", params={"months": 3}).json()}
    alpha = r["Insight Alpha Ltd"]
    assert abs(Decimal(alpha["annual_value"]) - Decimal("12000")) < 50 and alpha["reseller"] == "Insight Reseller GmbH"
    assert "no renewal deal" in alpha["flags"] and "no owner" in alpha["flags"]

    ret = client.get("/api/insights/retention", params={"year": Y}).json()
    kinds = {c["account"]: c["status"] for c in ret["customers"]}
    assert kinds["Insight Beta SA"] == "expanded" and kinds["Insight Gamma AG"] == "churned"
    assert ret["nrr"] is not None and ret["grr"] <= 100 and "data_from" in ret

    res = {x["reseller"]: x for x in client.get("/api/insights/resellers").json()}
    assert res["Insight Reseller GmbH"]["active_customers"] == 1
    assert Decimal(res["Insight Reseller GmbH"]["revenue_12m"]) >= Decimal("0")

    cr = client.get("/api/insights/credits").json()
    reb = [x for x in cr["rebilled"] if x["account"] == "Insight Delta Co"]
    assert reb and reb[0]["credit_lines"] == 2 and Decimal(reb[0]["credited"]) == Decimal("160.00")
    assert any(x["document"] == "CM1" for x in cr["lines"])

    ws = client.get("/api/insights/whitespace").json()
    lonely = next(s for s in ws["suggestions"] if s["account"] == "Insight Lonely Storage")
    assert lonely["suggest"][0]["family"] == "Hardware" and lonely["suggest"][0]["because"] == "Storage"
    assert insights.family("Sentry Bundle for BMC Helix Operations Management - Resource Unit").startswith("Bundle")

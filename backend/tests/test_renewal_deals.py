"""Renewal opportunities opened from licences 60 days before they renew (invented customers only)."""
import datetime as dt
from decimal import Decimal

from app import entitlements as ent
from app import renewal_deals
from app.db import SessionLocal
from app.models import Entitlement, Opportunity
from app.mzd_report import Report, ReportLine

TODAY = dt.date.today()


def _line(doc, customer, product, start, end, qty, net, fee, kind="term", reseller="Renew Reseller GmbH"):
    return ReportLine(doc_number=doc, doc_date=start, customer=customer, country="Germany", billing_company=reseller,
                      product=product, license_type=kind, start=start, end=end, term_days=(end - start).days + 1,
                      quantity=Decimal(qty), net=Decimal(net), fee=Decimal(fee), page=1)


def _year_ending(days):
    end = TODAY + dt.timedelta(days=days)
    return end - dt.timedelta(days=364), end


def test_one_renewal_opportunity_per_customer_with_a_line_per_licence(client):
    s1, e1 = _year_ending(30)
    s2, e2 = _year_ending(45)
    s3, e3 = _year_ending(90)
    q1 = TODAY - dt.timedelta(days=20)
    lines = [
        _line("RN1", "Renewco Bank AG", "Sentry Hardware Monitor for BMC Helix Operations Management", s1, e1, 500,
              "12000.00", "6120.00"),
        _line("RN1", "Renewco Bank AG", "Sentry Storage Monitor for BMC Helix Operations Management", s2, e2, 80,
              "2400.00", "1224.00"),
        _line("RN2", "Renewco Bank AG", "Sentry Backup Monitor", s3, e3, 10, "300.00", "153.00"),  # 90 days: later
        _line("RN3", "Quarterly Cloud SA", "Sentry Bundle", q1, q1 + dt.timedelta(days=89), 40, "900.00", "459.00",
              kind="saas"),  # billed quarterly: no renewal opportunity each quarter
    ]
    with SessionLocal() as db:
        ent.import_report(db, Report(title="t", lines=lines, warnings=[]), "renew.xlsx", dry_run=False)

    with SessionLocal() as db:
        preview = renewal_deals.open_renewal_opportunities(db, dry_run=True)
        mine = [p for p in preview.planned if p.account == "Renewco Bank AG"]
        assert len(mine) == 1 and mine[0].action == "create" and len(mine[0].licences) == 2
        assert not [p for p in preview.planned if p.account == "Quarterly Cloud SA"]
        assert not db.query(Opportunity).filter(Opportunity.title.like("Renewco Bank AG%")).count()  # dry run

        res = renewal_deals.open_renewal_opportunities(db)
        opp_id = next(p.opportunity_id for p in res.planned if p.account == "Renewco Bank AG")
        assert res.created >= 1 and opp_id
    r = client.post("/api/licences/renewal-opportunities", json={"dry_run": False})
    assert r.json()["created"] == 0 and not [p for p in r.json()["planned"] if p["account"] == "Renewco Bank AG"]

    opp = client.get(f"/api/opportunities/{opp_id}").json()
    assert opp["deal_type"] == "renewal" and opp["stage"]["name"] == "Upcoming renewal"
    assert opp["expected_close_date"] == e1.isoformat()
    assert opp["contract_start"] == (e1 + dt.timedelta(days=1)).isoformat() and opp["term_months"] == 12
    assert opp["route_to_market"] == "bmc_marketzone" and opp["reseller"]["name"] == "Renew Reseller GmbH"
    hw, st = opp["line_items"]
    assert hw["name"].startswith("Sentry Hardware Monitor") and Decimal(hw["quantity"]) == 500
    assert Decimal(hw["line_total"]) == Decimal("12000.00") and hw["term_months"] == 12
    assert "invoiced USD 12,000.00, Sentry fee USD 6,120.00" in hw["description"] and "RN1" in hw["description"]
    assert Decimal(opp["amount_tcv"]) == Decimal("14400.00")
    licences = client.get(f"/api/accounts/{opp['account_id']}/licences").json()
    linked = {h["product_name"]: h["renewal_opportunity_id"] for h in licences["holdings"]}
    assert linked["Sentry Backup Monitor"] is None and set(linked.values()) == {None, opp["id"]}

    # 50 days on, the backup licence (renewing then in 40 days) joins the open opportunity
    with SessionLocal() as db:
        res = renewal_deals.open_renewal_opportunities(db, today=TODAY + dt.timedelta(days=50))
        assert res.added >= 1
    opp = client.get(f"/api/opportunities/{opp['id']}").json()
    assert [li["name"] for li in opp["line_items"]][-1] == "Sentry Backup Monitor"
    assert Decimal(opp["amount_tcv"]) == Decimal("14700.00")


def test_customer_with_its_own_renewal_deal_gets_a_note_instead(client, ref):
    s, e = _year_ending(20)
    with SessionLocal() as db:
        ent.import_report(db, Report(title="t", lines=[_line("RN9", "Handmade Renewals Ltd", "Sentry Storage Monitor",
                                                                 s, e, 5, "100.00", "51.00")], warnings=[]),
                          "own.xlsx", dry_run=False)
        acc = db.query(Entitlement).filter(Entitlement.source_ref == "RN9").one().account_id
    own = client.post("/api/opportunities", json={"title": "Handmade renewal", "account_id": acc,
                                                  "brand_id": ref["brands"]["SENTRY"], "deal_type": "renewal"}).json()
    with SessionLocal() as db:
        res = renewal_deals.open_renewal_opportunities(db)
        plan = next(p for p in res.planned if p.account == "Handmade Renewals Ltd")
        assert plan.action == "note" and plan.opportunity_id == own["id"]
    notes = client.get("/api/activities", params={"opportunity_id": own["id"]}).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any("Sentry Storage Monitor" in (a["body"] or "") for a in items)
    assert client.get(f"/api/opportunities/{own['id']}").json()["line_items"] == []  # left as it was

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from app.bmc_quote import QuoteError, parse

# An approval email copied from Outlook: cells separated by tabs (a shortened copy of a real quote)
QUOTE = """Approvals List
Step Name\tApproval Status\tDate\tAssigned To\tDepends On\tActual Approver\tApprover Comments
Controlled Availability/Transitional Products/Bucket Deals Approvals\tOn Hold\t30-OCT-2026\tTed Brenner\t\t\tOn-Hold for consolidation - System
Notification to Sales Rep\tNotified\t30-OCT-2026\tKunal Pednekar\t\t\tNotified - System
Marketzone Products Approval\tAssigned\t30-OCT-2026\tTejas Rudrakanthwar\t\t\t

Product Details - General Information
Revenue Type\tProduct Name\tSupport Tier\tProduct Line\tAction\tTotal Discount\tQty\tStart Date\tEnd Date\tExpected BRV (USD)\tExpected ERV (USD)\tTotal Charge (USD)\tACV\tSubprocessor Update Justification
License\tNetreo Ultimate On-Prem Edition : managed device : OPS\tBMC Continuous Support\tITOM\tUpdateProduct\t98.80\t18500\t30-DEC-2026\t29-DEC-2027\t1,402.44\t68,928.85\t43,999.15\tUSD 43,999.15 (USD 43,999.15)\t-
License\tTrueSight Automation Suite - Base License : enterprise : OPS\tBMC Continuous Support\tRemediate\tUpdateProduct\t97.11\t1\t30-DEC-2026\t29-DEC-2027\t324.39\t324.39\t324.00\tUSD 324.00 (USD 324.00)\t-
License\tSentry Storage Monitor for BHOM OnPrem - MZ : managed asset - average Port : OPS\tBMC Continuous Support\tITOM\tUpdateProduct\t94.22\t984\t30-DEC-2026\t29-DEC-2027\t10,668.24\t10,668.24\t10,668.00\tUSD 10,668.00 (USD 10,668.00)\t-
License\tSentry Hardware Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS\tBMC Continuous Support\tITOM\tUpdateProduct\t94.22\t1300\t30-DEC-2026\t29-DEC-2027\t33,231.95\t33,231.95\t33,232.00\tUSD 33,232.00 (USD 33,232.00)\t-
License\tSentry Backup Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS\tBMC Continuous Support\tITOM\tUpdateProduct\t94.22\t21\t30-DEC-2026\t29-DEC-2027\t748.21\t748.21\t748.00\tUSD 748.00 (USD 748.00)\t-
License\tEntuity Network Analyzer for BMC - MZ : managed asset - device endpoint : OPS\tBMC Continuous Support\tCVT\tUpdateProduct\t99.00\t18500\t30-DEC-2026\t30-JUN-2027\t34,506.07\t34,506.07\t34,412.01\tUSD 58,992.02 (USD 58,992.02)\t-
License\tBHCO OnPrem for Storage Plus : managed asset - average Port : OPS\tBMC Continuous Support\tITOM\tUpdateProduct\t96.96\t984\t30-DEC-2026\t29-DEC-2027\t5,250.44\t5,250.44\t5,512.50\tUSD 5,512.50 (USD 5,512.50)\t-

Product Details - Additional Pricing Information
Revenue Type\tProduct Name\tProduct Status\tProduct Line\tAction\tList Price (USD)\tRecurring Discount%\tTotal One Time Discount\tOne Time Discount Reasons\tBRV/Unit\tERV/Unit\tEffective Price (USD)\tYORG %
License\tNetreo Ultimate On-Prem Edition : managed device : OPS\tGenerally Available\tITOM\tUpdateProduct\t33.08\t96.47\t66.08\t\t0.01\t0.31\t0.20\t62.73%
License\tTrueSight Automation Suite - Base License : enterprise : OPS\tGenerally Available\tRemediate\tUpdateProduct\t1,869.27\t97.11\t0.00\t\t27.03\t27.03\t27.00\t0.00%
License\tSentry Storage Monitor for BHOM OnPrem - MZ : managed asset - average Port : OPS\tGenerally Available\tITOM\tUpdateProduct\t31.24\t94.22\t0.00\t\t0.90\t0.90\t0.90\t0.00%
License\tSentry Hardware Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS\tGenerally Available\tITOM\tUpdateProduct\t73.65\t94.22\t0.00\t\t2.13\t2.13\t2.13\t0.00%
License\tSentry Backup Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS\tGenerally Available\tITOM\tUpdateProduct\t102.66\t94.22\t0.00\t\t2.97\t2.97\t2.97\t0.00%
License\tEntuity Network Analyzer for BMC - MZ : managed asset - device endpoint : OPS\tTransition\tCVT\tUpdateProduct\t49.90\t99.00\t0.00\t\t0.31\t0.31\t0.31\t0.00%
License\tBHCO OnPrem for Storage Plus : managed asset - average Port : OPS\tTransition\tITOM\tUpdateProduct\t30.76\t96.96\t0.00\t\t0.44\t0.44\t0.47\t0.00%
"""


def as_pdf_text(text: str) -> str:
    """The same quote copied from a PDF: no tabs, long cells wrapped onto several lines."""
    out = text.replace("\t", " ")
    return out.replace("managed asset - average", "managed asset -\naverage").replace("BMC Continuous Support",
                                                                                     "BMC Continuous\nSupport")


@pytest.mark.parametrize("text", [QUOTE, as_pdf_text(QUOTE)], ids=["outlook", "pdf"])
def test_parse_finds_sentry_lines(text):
    q = parse(text)
    assert len(q.lines) == 7
    names = [ln.name for ln in q.sentry_lines]
    assert names == [
        "Sentry Storage Monitor for BHOM OnPrem - MZ : managed asset - average Port : OPS",
        "Sentry Hardware Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS",
        "Sentry Backup Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS",
        "BHCO OnPrem for Storage Plus : managed asset - average Port : OPS",
    ]
    storage = q.sentry_lines[0]
    assert storage.quantity == 984 and storage.total_charge == Decimal("10668.00")
    assert storage.start == dt.date(2026, 12, 30) and storage.end == dt.date(2027, 12, 29)
    assert storage.term_months == 12 and storage.discount_pct == Decimal("94.22")
    assert storage.list_price == Decimal("31.24") and storage.effective_price == Decimal("0.90")
    assert storage.recurring_discount == Decimal("94.22")
    assert storage.status == "Generally Available" and storage.action == "UpdateProduct"
    assert q.sentry_lines[3].status == "Transition"
    assert sum(ln.total_charge for ln in q.sentry_lines) == Decimal("50160.50")
    assert q.currency == "USD"
    # the BMC rows around them are read too (they give the size of the whole quote)
    assert q.lines[0].name == "Netreo Ultimate On-Prem Edition : managed device : OPS"
    assert q.lines[1].name == "TrueSight Automation Suite - Base License : enterprise : OPS"
    assert q.lines[5].term_months == 6


def test_parse_approvals():
    q = parse(QUOTE)
    assert [(a.status, a.assigned_to) for a in q.approvals] == [
        ("On Hold", "Ted Brenner"), ("Notified", "Kunal Pednekar"), ("Assigned", "Tejas Rudrakanthwar")]
    assert q.sales_rep == "Kunal Pednekar"
    assert parse(as_pdf_text(QUOTE)).sales_rep == "Kunal Pednekar"


def test_parse_rejects_text_without_products():
    with pytest.raises(QuoteError):
        parse("Approvals List\nNothing here")


def test_fingerprint_is_stable():
    assert parse(QUOTE).fingerprint() == parse(as_pdf_text(QUOTE)).fingerprint()
    assert parse("Quote Number: Q-123456\n" + QUOTE).fingerprint() == "Q:Q-123456"


def test_import_creates_sentry_opportunity(client):
    acct = client.post("/api/accounts", json={"name": "Quote Customer Inc", "account_type": "customer"}).json()
    rep = client.post("/api/contacts", json={"first_name": "Kunal", "last_name": "Pednekar",
                                             "email": "kunal.pednekar@bmc.example", "role": "partner_contact"}).json()

    r = client.post("/api/opportunities/bmc-quote/preview", json={"text": QUOTE})
    assert r.status_code == 200, r.text
    p = r.json()
    assert len(p["lines"]) == 4 and p["line_count"] == 7
    assert Decimal(p["sentry_total"]) == Decimal("50160.50")
    assert p["sales_rep"] == {"name": "Kunal Pednekar", "contact_id": rep["id"]}
    assert p["deal_type"] == "new" and p["existing"] is None
    assert p["contract_start"] == "2026-12-30" and p["contract_end"] == "2027-12-29"

    r = client.post("/api/opportunities/bmc-quote", json={"text": QUOTE, "account_id": acct["id"], "skip": [2]})
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["title"] == "Quote Customer Inc - Sentry via BMC"
    assert o["brand"]["name"] == "Sentry Software" and o["route_to_market"] == "bmc_marketzone"
    assert o["referring_platform"]["name"].startswith("BMC")
    assert o["partner_contact"]["id"] == rep["id"]
    assert o["stage"]["name"] == "Proposal / Follow-up"
    assert o["contract_start"] == "2026-12-30" and o["term_months"] == 12
    assert [li["name"] for li in o["line_items"]][2] == "BHCO OnPrem for Storage Plus : managed asset - average Port : OPS"
    assert len(o["line_items"]) == 3  # the backup line was left out
    # quantity, list price, recurring discount and term from the quote; worth the line's total charge
    storage = o["line_items"][0]
    assert (Decimal(storage["quantity"]), Decimal(storage["unit_price"]), Decimal(storage["discount_pct"]),
            storage["term_months"], storage["unit"]) == (984, Decimal("31.24"), Decimal("94.22"), 12, None)
    assert Decimal(storage["line_total"]) == Decimal(storage["fixed_total"]) == Decimal("10668.00")
    kept = [ln for i, ln in enumerate(p["lines"]) if i != 2]
    assert Decimal(o["amount_tcv"]) == sum(Decimal(ln["total_charge"]) for ln in kept)
    assert storage["description"].startswith("Qty 984 · total charge USD 10,668.00 · list USD 31.24/unit")
    assert Decimal(o["amount_tcv"]) == sum(Decimal(li["line_total"]) for li in o["line_items"])
    assert o["currency"] == "USD" and o["price_book_id"]
    notes = client.get("/api/activities", params={"opportunity_id": o["id"]}).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any("Approvals:" in (a["body"] or "") for a in items)

    # the same quote again: flagged in the preview, refused on import
    assert client.post("/api/opportunities/bmc-quote/preview", json={"text": QUOTE}).json()["existing"]["id"] == o["id"]
    r = client.post("/api/opportunities/bmc-quote", json={"text": QUOTE, "account_id": acct["id"]})
    assert r.status_code == 409


def test_import_refuses_quote_without_sentry_lines(client):
    bmc_only = "\n".join(ln for ln in QUOTE.splitlines() if "Sentry" not in ln and "Storage Plus" not in ln)
    r = client.post("/api/opportunities/bmc-quote/preview", json={"text": bmc_only})
    assert r.status_code == 422 and "none of them is a Sentry product" in r.json()["detail"]


def test_import_in_euros_at_total_charge(client):
    acct = client.post("/api/accounts", json={"name": "Euro Customer SA", "account_type": "customer"}).json()
    eur = QUOTE.replace("USD", "EUR").replace("30-DEC-2026", "22-FEB-2027")  # another quote, no EUR BMC price book
    r = client.post("/api/opportunities/bmc-quote", json={"text": eur, "account_id": acct["id"]})
    assert r.status_code == 201, r.text
    o = r.json()
    assert Decimal(o["amount_tcv"]) == Decimal("50160.50")
    assert all(li["unit"] is None and li["line_total"] == li["fixed_total"] for li in o["line_items"])
    books = {b["id"]: b["currency"] for b in client.get("/api/price-books").json()}
    assert o["currency"] == "EUR" and (o["price_book_id"] is None or books[o["price_book_id"]] == "EUR")


def test_line_without_pricing_row_keeps_total_charge(client):
    acct = client.post("/api/accounts", json={"name": "No Pricing Rows Ltd", "account_type": "customer"}).json()
    general_only = QUOTE.split("Product Details - Additional Pricing Information")[0].replace("30-DEC-2026", "01-JAN-2027")
    o = client.post("/api/opportunities/bmc-quote", json={"text": general_only, "account_id": acct["id"]}).json()
    assert {li["unit"] for li in o["line_items"]} == {"deal_total"}
    assert Decimal(o["amount_tcv"]) == Decimal("50160.50")


def test_fixed_total_survives_an_edit_and_wins_over_the_price(client):
    acct = client.post("/api/accounts", json={"name": "Fixed Total GmbH", "account_type": "customer"}).json()
    quote = QUOTE.replace("30-DEC-2026", "05-JAN-2027")
    o = client.post("/api/opportunities/bmc-quote", json={"text": quote, "account_id": acct["id"]}).json()
    lines = [{k: li[k] for k in ("name", "description", "quantity", "unit_price", "discount_pct", "term_months",
                                 "billing_type", "fixed_total")} for li in o["line_items"]]
    r = client.patch(f"/api/opportunities/{o['id']}", json={"line_items": lines})
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["amount_tcv"]) == Decimal("50160.50")


SAAS_QUOTE = (Path(__file__).parent / "fixtures" / "bmc_quote_saas.txt").read_text(encoding="utf-8")


def test_saas_quote_without_brv_erv_columns(client):
    # SaaS quotes have no Expected BRV / ERV columns, no BRV / ERV per unit and an empty YORG %
    q = parse(SAAS_QUOTE)
    assert len(q.lines) == 3 and (q.quote_number, q.customer) == ("Q137501", "State Employees Credit Union")
    (line,) = q.sentry_lines
    assert line.name == "Sentry Bundle for BMC Helix Operations Management - MZ : resource unit : SaaS"
    assert (line.quantity, line.total_charge, line.term_months) == (78, Decimal("14376.96"), 36)
    assert (line.list_price, line.recurring_discount, line.effective_price) == (
        Decimal("80.18"), Decimal("89.36"), Decimal("5.12"))
    assert q.sales_rep == "Michael Loftin" and len(q.approvals) == 5

    acct = client.post("/api/accounts", json={"name": "State Employees Credit Union", "account_type": "customer"}).json()
    p = client.post("/api/opportunities/bmc-quote/preview", json={"text": SAAS_QUOTE}).json()
    assert p["account"]["id"] == acct["id"] and p["deal_type"] == "new"
    o = client.post("/api/opportunities/bmc-quote", json={"text": SAAS_QUOTE, "account_id": acct["id"]}).json()
    assert Decimal(o["amount_tcv"]) == Decimal("14376.96") and o["term_months"] == 36

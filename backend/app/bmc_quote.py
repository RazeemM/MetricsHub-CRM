"""Reader for BMC quote approval emails: finds the Sentry products in a quote pasted as text.

The approval email has an "Approvals List" and two product tables, one row per product in each:
  * General Information: Revenue Type | Product Name | Support Tier | Product Line | Action | Total Discount | Qty
    | Start Date | End Date | Expected BRV | Expected ERV | Total Charge | ACV | Subprocessor Update Justification
  * Additional Pricing: Revenue Type | Product Name | Product Status | Product Line | Action | List Price
    | Recurring Discount% | Total One Time Discount | One Time Discount Reasons | BRV/Unit | ERV/Unit
    | Effective Price | YORG %
Copied from Outlook or a browser the cells are separated by tabs; copied from a PDF they are separated by spaces and
long names wrap onto several lines. So rows are read from the text with all whitespace collapsed, by their shape:
a product name ending in " : <licence model>" followed by the numbers and dates of that table.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal

from .pricing import months_between

# BMC product names of Sentry products (OnPrem and SaaS). Any product with "Sentry" in its name counts too.
SENTRY_PRODUCTS = [
    "Sentry Storage Monitor for BHOM OnPrem - MZ : managed asset - average Port : OPS",
    "Sentry Hardware Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS",
    "Sentry Backup Monitor for BHOM OnPrem - MZ : managed asset - average Server Endpoint : OPS",
    "BHCO OnPrem for Storage Plus : managed asset - average Port : OPS",
    "BHOM - AIOps Add-on for Serverless Assets (250-Pack) : asset - average Serverless Asset : SaaS",
    "Sentry Storage Monitor for BHOM - MZ : asset - average port : SaaS",
    "Sentry Monitoring Studio for BHOM for Servers - MZ : asset - average server endpoint : SaaS",
    "Sentry Hardware Monitor for BHOM - MZ : asset - average server endpoint : SaaS",
    "BHCO for Storage Plus : asset - average port : SaaS",
    "Sentry Bundle for BMC Helix Continuous Optimization - MZ : resource unit : SaaS",
    "Sentry Bundle for BMC Helix Operations Management - MZ : resource unit : SaaS",
]

REVENUE = r"(?:Term License|License|Subscription|SaaS|Support|Maintenance|Services?)"
DATE = r"\d{1,2}-[A-Za-z]{3}-\d{4}"
# a name or text cell never runs over a date or a column header ("Support Tier" in the header is not a row)
NO_DATE = rf"(?:(?!{DATE}|\bQty\b|Start Date|Total Charge|List Price|Product Line|Product Status).)"
MONEY = r"-?[\d,]*\d\.\d{2}"
NUM = r"-?[\d,]*\d(?:\.\d+)?"
# the name ends with its licence model: "... : OPS", "... : SaaS"
NAME = rf"(?P<name>[A-Za-z0-9(]{NO_DATE}{{2,240}}? : (?:OPS|SaaS|SAAS|[A-Z]{{2,6}}))"

GENERAL = re.compile(
    rf"\b(?P<rev>{REVENUE}) {NAME} (?P<mid>{NO_DATE}{{0,120}}?) ?(?P<disc>{NUM}) (?P<qty>{NUM}) "
    rf"(?P<start>{DATE}) (?P<end>{DATE}) (?P<brv>{MONEY}) (?P<erv>{MONEY}) (?P<charge>{MONEY}) "
    rf"(?P<cur>[A-Z]{{3}}) ?(?P<acv>{MONEY})")
PRICING = re.compile(
    rf"\b(?P<rev>{REVENUE}) {NAME} (?P<mid>[^\d]{{0,80}}?) ?(?P<list>{MONEY}) (?P<disc>{NUM}) (?P<otd>{MONEY}) "
    rf"(?:(?P<reason>[^\d]{{1,160}}?) )?(?P<brvu>{MONEY}) (?P<ervu>{MONEY}) (?P<eff>{MONEY}) (?P<yorg>{NUM}) ?%")
STATUSES = ("Generally Available", "Withdrawn", "Transition", "Controlled Availability", "End of Life", "Retired")
APPROVAL_STATUS = r"On Hold|Assigned|Notified|Approved|Rejected|Pending|Completed|Skipped|Cancell?ed|Recalled"
APPROVAL = re.compile(rf"^(?P<step>.+?)\s+(?P<status>{APPROVAL_STATUS})\s+(?P<date>{DATE})\s+"
                      r"(?P<who>[A-Z][\w.'-]+(?: [A-Z][\w.'-]+)?)", re.I)
QUOTE_NUMBER = re.compile(r"\bQuote\s*(?:Number|No\.?|Num|#|ID)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{3,40})", re.I)
CUSTOMER = re.compile(r"^\s*(?:Customer|Account|End Customer|End User|Sold To)(?: Name)?\s*[:\t]\s*(.{2,120}?)\s*$",
                      re.I | re.M)


class QuoteError(ValueError):
    pass


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().lower()


SENTRY_KEYS = {norm(n) for n in SENTRY_PRODUCTS}


def is_sentry(name: str) -> bool:
    return norm(name) in SENTRY_KEYS or "sentry" in name.lower()


def _dec(s: str | None) -> Decimal:
    return Decimal((s or "0").replace(",", "") or "0")


def _date(s: str) -> dt.date:
    return dt.datetime.strptime(s, "%d-%b-%Y").date()


@dataclass
class QuoteLine:
    name: str
    revenue_type: str
    details: str  # support tier, product line, action
    discount_pct: Decimal
    quantity: Decimal
    start: dt.date
    end: dt.date
    expected_brv: Decimal
    expected_erv: Decimal
    total_charge: Decimal
    currency: str
    acv: Decimal
    sentry: bool
    status: str | None = None
    list_price: Decimal | None = None
    recurring_discount: Decimal | None = None
    effective_price: Decimal | None = None

    @property
    def term_months(self) -> int:
        return max(months_between(self.start, self.end), 1)

    @property
    def priced(self) -> bool:
        """The pricing table gave this line a list price and a recurring discount."""
        return self.list_price is not None and self.recurring_discount is not None and self.quantity > 0

    @property
    def action(self) -> str:
        return self.details.split(" ")[-1] if self.details else ""

    def description(self) -> str:
        """What the CRM line keeps of the quote line."""
        parts = [f"Qty {self.quantity.normalize():,f}", f"total charge {self.currency} {self.total_charge:,.2f}"]
        if self.list_price is not None:
            parts.append(f"list {self.currency} {self.list_price:,.2f}/unit")
        if self.effective_price is not None:
            parts.append(f"effective {self.currency} {self.effective_price:,.2f}/unit")
        parts.append(f"total discount {self.discount_pct}%")
        parts.append(f"{self.start:%d %b %Y} to {self.end:%d %b %Y}")
        if self.status:
            parts.append(self.status)
        if self.details:
            parts.append(self.details)
        return " · ".join(parts)


@dataclass
class Approval:
    step: str
    status: str
    date: str
    assigned_to: str


@dataclass
class ParsedQuote:
    lines: list[QuoteLine]
    approvals: list[Approval] = field(default_factory=list)
    quote_number: str | None = None
    customer: str | None = None

    @property
    def sentry_lines(self) -> list[QuoteLine]:
        return [ln for ln in self.lines if ln.sentry]

    @property
    def currency(self) -> str:
        return self.lines[0].currency if self.lines else "USD"

    @property
    def sales_rep(self) -> str | None:
        return next((a.assigned_to for a in self.approvals if "sales rep" in a.step.lower()), None)

    def fingerprint(self) -> str:
        """Identifies the quote for duplicate checks: its number, or a hash of its Sentry lines."""
        if self.quote_number:
            return f"Q:{self.quote_number}"
        key = "|".join(f"{norm(ln.name)};{ln.quantity};{ln.start};{ln.end};{ln.total_charge}"
                       for ln in self.sentry_lines)
        return "H:" + hashlib.sha256(key.encode()).hexdigest()[:40]


def _split_mid(mid: str) -> tuple[str | None, str]:
    """Product status at the start of the pricing row's text columns ("Generally Available ITOM UpdateProduct")."""
    for s in STATUSES:
        if mid.lower().startswith(s.lower()):
            return s, mid[len(s):].strip()
    return None, mid


def parse(text: str) -> ParsedQuote:
    flat = re.sub(r"\s+", " ", text or "")
    lines: dict[str, QuoteLine] = {}
    order: list[QuoteLine] = []
    for m in GENERAL.finditer(flat):
        name = m["name"].strip()
        ln = QuoteLine(
            name=name, revenue_type=m["rev"], details=m["mid"].strip(), discount_pct=_dec(m["disc"]),
            quantity=_dec(m["qty"]), start=_date(m["start"]), end=_date(m["end"]), expected_brv=_dec(m["brv"]),
            expected_erv=_dec(m["erv"]), total_charge=_dec(m["charge"]), currency=m["cur"], acv=_dec(m["acv"]),
            sentry=is_sentry(name))
        if ln.end < ln.start:
            raise QuoteError(f"{name}: the end date is before the start date")
        order.append(ln)
        lines.setdefault(norm(name), ln)
    if not order:
        raise QuoteError("No product lines found. Copy the whole quote, including the \"Product Details - General "
                         "Information\" table with its quantities, dates and charges.")
    for m in PRICING.finditer(flat):
        ln = lines.get(norm(m["name"]))
        if ln and ln.list_price is None:
            ln.status, _ = _split_mid(m["mid"].strip())
            ln.list_price, ln.effective_price = _dec(m["list"]), _dec(m["eff"])
            ln.recurring_discount = _dec(m["disc"])

    approvals = []
    for raw in (text or "").splitlines():
        cells = [c.strip() for c in raw.split("\t")]
        if len(cells) >= 4 and re.fullmatch(APPROVAL_STATUS, cells[1], re.I) and re.fullmatch(DATE, cells[2]):
            approvals.append(Approval(cells[0], cells[1], cells[2], cells[3]))
        elif m := APPROVAL.match(raw.strip()):
            approvals.append(Approval(m["step"], m["status"], m["date"], m["who"]))
    number = QUOTE_NUMBER.search(text or "")
    customer = CUSTOMER.search(text or "")
    return ParsedQuote(order, approvals, number[1] if number else None, customer[1] if customer else None)

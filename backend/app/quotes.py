"""Quote templates, quote numbering, HTML rendering and PDF generation."""
import base64
import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Account, Brand, Contact, Opportunity, Product, Quote, QuoteTemplate
from .pricing import compute_totals

BASE = Path(__file__).parent
env = Environment(loader=FileSystemLoader(BASE / "templates"), autoescape=select_autoescape(["html"]))

TEMPLATE_FIELDS = [
    "company_name", "address", "vat_number", "registration", "email", "phone", "website", "logo_data_uri",
    "logo_height", "header_show_name", "header_bg", "header_text_color", "accent_color", "title", "intro_text", "terms_text",
    "payment_terms", "validity_days", "footer_text", "show_discount", "show_signature", "email_subject", "email_body",
]

# Placeholders users can put in intro, terms, payment terms and footer
PLACEHOLDERS = {
    "{customer}": "Customer account name",
    "{contact}": "Primary contact name",
    "{quote_number}": "Quote number",
    "{valid_until}": "Expiry date",
    "{term_months}": "Contract period in months",
    "{currency}": "Currency code",
    "{owner}": "Opportunity owner",
    "{company}": "Your company name",
}

_SAMPLE_TERMS = """1. Prices are exclusive of VAT and any applicable taxes.
2. Subscriptions are billed annually in advance unless stated otherwise.
3. Recurring prices are per unit per month for the contract period shown above.
4. This quotation is valid until {valid_until}. Prices may change after this date.
5. All orders are subject to the {company} General Terms and Conditions.

PLACEHOLDER TEXT: have your legal team review and replace these terms."""


DEFAULT_EMAIL_SUBJECT = "{company} quotation {quote_number} for {customer}"
DEFAULT_EMAIL_BODY = """Dear {contact},

Please find attached our quotation {quote_number} for {customer}, valid until {valid_until}.

Do not hesitate to reply to this email with any question.

Best regards,
{owner}
{company}"""


def _logo(filename: str) -> str | None:
    path = BASE / "assets" / filename
    if not path.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def default_template(brand: Brand) -> dict:
    sentry = brand.code == "SENTRY"
    return {
        "company_name": "Sentry Software" if sentry else "MetricsHub S.A.S.",
        "address": "[Street address]\n[Postcode, City]\n[Country]",
        "vat_number": "[VAT number]",
        "registration": None,
        "email": None,
        "phone": None,
        "website": (brand.website or "").removeprefix("https://").removeprefix("www.") or None,
        "logo_data_uri": _logo("sentry-logo-white.png" if sentry else "metricshub-icon.png"),
        "logo_height": 36,
        "header_show_name": not sentry,  # the Sentry logo already contains the company name
        "header_bg": "#131A24" if sentry else "#141A22",
        "header_text_color": "#FFFFFF",
        "accent_color": "#F28C38" if sentry else "#7C5CFF",
        "title": "Quotation",
        "intro_text": "Dear {contact},\n\nThank you for your interest. Please find below our proposal for {customer}. "
                      "Do not hesitate to contact {owner} with any question.",
        "terms_text": _SAMPLE_TERMS,
        "payment_terms": "Net 30 days from invoice date",
        "validity_days": 30,
        "footer_text": "{company} · Thank you for your business",
        "show_discount": True,
        "show_signature": True,
        "email_subject": DEFAULT_EMAIL_SUBJECT,
        "email_body": DEFAULT_EMAIL_BODY,
    }


def get_or_create_template(db: Session, brand_id: int) -> QuoteTemplate:
    tpl = db.scalar(select(QuoteTemplate).where(QuoteTemplate.brand_id == brand_id))
    if tpl:
        return tpl
    brand = db.get(Brand, brand_id)
    tpl = QuoteTemplate(brand_id=brand_id, **default_template(brand))
    db.add(tpl)
    db.flush()
    return tpl


def template_dict(tpl: QuoteTemplate) -> dict:
    return {f: getattr(tpl, f) for f in TEMPLATE_FIELDS}


# ---------------- numbering ----------------
def next_number(db: Session, brand: Brand, today: dt.date) -> str:
    prefix = f"{brand.quote_prefix}-Q-{today.year}-"
    # Serialize numbering per brand: lock the brand row for the rest of the transaction
    db.execute(select(Brand.id).where(Brand.id == brand.id).with_for_update())
    last = db.scalar(select(func.max(Quote.number)).where(Quote.number.like(f"{prefix}%")))
    seq = int(last.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{seq:04d}"


# ---------------- snapshot ----------------
def build_quote(db: Session, opp: Opportunity, user_id: int | None, valid_days: int | None = None,
                notes: str | None = None) -> Quote:
    tpl = get_or_create_template(db, opp.brand_id)
    brand = db.get(Brand, opp.brand_id)
    today = dt.date.today()
    previous = db.scalar(select(Quote).where(Quote.opportunity_id == opp.id).order_by(Quote.id.desc()))
    if previous:
        number, version = previous.number, previous.version + 1
    else:
        number, version = next_number(db, brand, today), 1

    account: Account = opp.account
    contact: Contact | None = opp.primary_contact
    customer = {
        "name": account.name,
        "address": account.address,
        "city": account.city,
        "country": account.country,
        "vat_number": account.vat_number,
        "contact_name": contact.full_name if contact else None,
        "contact_email": contact.email if contact else None,
        "contact_title": contact.job_title if contact else None,
    }
    lines = []
    for li in opp.line_items:
        product = db.get(Product, li.product_id) if li.product_id else None
        lines.append({
            "name": li.name,
            "sku": product.sku if product else None,
            "description": li.description or (product.description if product else None),
            "unit": li.unit,
            "billing_type": li.billing_type,
            "quantity": str(li.quantity),
            "unit_price": str(li.unit_price),
            "discount_pct": str(li.discount_pct),
            "term_months": li.term_months or opp.term_months,
            "line_total": str(li.line_total),
        })
    totals = compute_totals(opp.line_items, opp.term_months)
    days = valid_days if valid_days is not None else tpl.validity_days
    return Quote(
        opportunity_id=opp.id, brand_id=opp.brand_id, number=number, version=version, status="draft",
        issue_date=today, valid_until=today + dt.timedelta(days=days), currency=opp.currency,
        term_months=opp.term_months, contract_start=opp.contract_start, contract_end=opp.contract_end,
        customer=customer, lines=lines, amount_tcv=totals.tcv, amount_arr=totals.arr,
        amount_recurring=totals.recurring, amount_one_time=totals.one_time, template=template_dict(tpl),
        notes=notes, created_by_id=user_id,
    )


# ---------------- rendering ----------------
CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}
UNIT_LABELS = {"host": "host", "resource_unit": "RU", "physical_system": "system",
               "front_end_ports_5": "5 FE ports", "service_day": "day", "license": "license"}


def fmt_money(v, currency: str) -> str:
    d = Decimal(str(v or 0)).quantize(Decimal("0.01"))
    sym = CURRENCY_SYMBOLS.get(currency)
    s = f"{d:,.2f}"
    return f"{sym}{s}" if sym else f"{s} {currency}"


def fmt_qty(v) -> str:
    d = Decimal(str(v or 0))
    return f"{d:,.0f}" if d == d.to_integral() else f"{d:,.2f}"


def fmt_date(d, short: bool = False) -> str:
    if not d:
        return "—"
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    return d.strftime("%d %b %Y" if short else "%d %B %Y")


def fill(text: str | None, values: dict) -> str:
    if not text:
        return ""
    for key, val in values.items():
        text = text.replace(key, str(val or ""))
    return text


def rich(text: str) -> Markup:
    """Plain text to safe HTML: blank line = paragraph, '- ' or '• ' = bullet, **bold**."""
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.split("\n")
        if all(re.match(r"^\s*[-•]\s+", ln) for ln in lines if ln.strip()):
            items = "".join(f"<li>{_inline(re.sub(r'^\s*[-•]\s+', '', ln))}</li>" for ln in lines if ln.strip())
            out.append(f"<ul>{items}</ul>")
        else:
            out.append("<p>" + "<br>".join(_inline(ln) for ln in lines) + "</p>")
    return Markup("".join(out))


def _inline(s: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", str(escape(s)))


def placeholder_values(quote_data: dict, template: dict) -> dict:
    return {
        "{customer}": quote_data["customer"].get("name"),
        "{contact}": quote_data["customer"].get("contact_name") or quote_data["customer"].get("name"),
        "{quote_number}": quote_data["display_number"],
        "{valid_until}": fmt_date(quote_data["valid_until"]),
        "{term_months}": quote_data["term_months"],
        "{currency}": quote_data["currency"],
        "{owner}": quote_data.get("owner") or "",
        "{company}": template.get("company_name") or "",
    }


def render_html(quote_data: dict, template: dict) -> str:
    values = placeholder_values(quote_data, template)
    t = dict(template)
    for key in ("intro_text", "terms_text", "footer_text"):
        t[key] = rich(fill(t.get(key), values)) if t.get(key) else ""
    t["payment_terms"] = fill(t.get("payment_terms"), values)
    has_discount = any(Decimal(str(ln["discount_pct"])) > 0 for ln in quote_data["lines"])
    return env.get_template("quote.html").render(
        q=quote_data, t=t, money=lambda v: fmt_money(v, quote_data["currency"]), qty=fmt_qty, date=fmt_date,
        units=UNIT_LABELS, show_discount=t.get("show_discount") and has_discount,
    )


def quote_to_data(q: Quote, owner: str | None = None) -> dict:
    return {
        "display_number": q.number if q.version == 1 else f"{q.number} v{q.version}",
        "issue_date": q.issue_date, "valid_until": q.valid_until, "currency": q.currency,
        "term_months": q.term_months, "contract_start": q.contract_start, "contract_end": q.contract_end,
        "customer": q.customer, "lines": q.lines, "tcv": q.amount_tcv, "arr": q.amount_arr,
        "recurring": q.amount_recurring, "one_time": q.amount_one_time, "notes": q.notes, "owner": owner,
        "status": q.status,
    }


def sample_data() -> dict:
    """Example quote used for the live template preview."""
    today = dt.date.today()
    return {
        "display_number": "MH-Q-2026-0042", "issue_date": today, "valid_until": today + dt.timedelta(days=30),
        "currency": "USD", "term_months": 36, "contract_start": today + dt.timedelta(days=31),
        "contract_end": today + dt.timedelta(days=31 + 3 * 365),
        "customer": {"name": "Example Customer Ltd", "address": "1 Example Street", "city": "Paris",
                     "country": "France", "vat_number": "FR00000000000", "contact_name": "Jane Example",
                     "contact_email": "jane@example.com", "contact_title": "Head of Infrastructure"},
        "lines": [
            {"name": "Enterprise subscription", "sku": "SKU-001", "description": "Per monitored host per month",
             "unit": "host", "billing_type": "recurring", "quantity": "500", "unit_price": "15.00",
             "discount_pct": "20", "term_months": 36, "line_total": "216000.00"},
            {"name": "Professional services (day)", "sku": "SKU-002", "description": "Deployment assistance",
             "unit": "service_day", "billing_type": "one_time", "quantity": "3", "unit_price": "1400.00",
             "discount_pct": "0", "term_months": 36, "line_total": "4200.00"},
        ],
        "tcv": Decimal("220200.00"), "arr": Decimal("72000.00"), "recurring": Decimal("216000.00"),
        "one_time": Decimal("4200.00"), "notes": None, "owner": "Account Manager", "status": "draft",
    }


def render_pdf(html: str) -> bytes:
    from weasyprint import HTML  # imported lazily: heavy native dependency

    from weasyprint.urls import URLFetcher

    # Only embedded data: URIs may load while rendering: no outbound requests, no local files
    fetcher = URLFetcher(allowed_protocols=["data"], allow_redirects=False)
    return HTML(string=html, url_fetcher=fetcher).write_pdf()

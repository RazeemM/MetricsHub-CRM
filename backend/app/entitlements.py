"""Customer licences (entitlements): report import, per-product holdings, renewal notices and lapses."""
from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import mail
from .config import get_settings
from .models import Account, Brand, Entitlement, Notification, Opportunity, Pipeline, Stage, User
from .mzd_report import Report

LEGAL = re.compile(r"\b(inc|incorporated|llc|ltd|limited|plc|corp|corporation|co|kg|gmbh|ag|sa|s a|sas|bv|b v|nv|"
                   r"spa|srl|pte|pvt|private|company|wll|the)\b")


def norm_name(name: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (name or "").lower())
    s = LEGAL.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------------- holdings
@dataclass
class Holding:
    """What a customer owns of one product, summarised from its licence lines."""

    account_id: int
    account_name: str
    product_name: str
    license_type: str
    quantity: Decimal
    period_start: dt.date | None
    period_end: dt.date | None
    renewal_date: dt.date | None
    status: str  # active, renewal_due, awaiting_report, lapsed, upcoming, cancelled
    installments: bool  # billed in periods shorter than a year (e.g. quarterly SaaS): no renewal notice
    days_to_renewal: int | None
    reseller: str | None
    latest_line_id: int
    resolved: bool
    resolution: str | None = None
    resolved_by: str | None = None
    resolved_at: dt.datetime | None = None
    lines: list[int] = field(default_factory=list)
    later_purchase: dict | None = None  # lapsed: the customer's latest purchase of another product afterwards


INSTALMENT_DAYS = 200  # a paid period shorter than this (quarterly, half-yearly) is a billing instalment, not a term


def _holding(lines: list[Entitlement], today: dt.date, notice_days: int, report_cutoff: dt.date | None) -> Holding:
    """report_cutoff: latest invoice date in the imported MarketZone reports. A report licence that ended after it
    may still have been renewed by an invoice the next report will show, so it is not lapsed yet."""
    latest = max(lines, key=lambda e: (e.end_date or dt.date.min, e.id))
    reseller = next((e.reseller.name for e in sorted(lines, key=lambda e: e.end_date or dt.date.min, reverse=True)
                     if e.reseller), None)
    common = dict(
        account_id=latest.account_id, account_name=latest.account.name, product_name=latest.product_name,
        license_type=latest.license_type, reseller=reseller, latest_line_id=latest.id,
        resolved=latest.lapse_resolved_at is not None, resolution=latest.lapse_resolution,
        resolved_by=latest.lapse_resolved_by.full_name if latest.lapse_resolved_by else None,
        resolved_at=latest.lapse_resolved_at, lines=[e.id for e in lines])
    if latest.license_type == "perpetual":
        # owned for good: no renewal date, never lapses (its maintenance is a separate Support licence)
        qty = sum((e.quantity for e in lines), Decimal(0))
        return Holding(**common, quantity=qty, period_start=min((e.start_date for e in lines if e.start_date),
                                                                default=None),
                       period_end=None, renewal_date=None, status="perpetual" if qty > 0 else "cancelled",
                       installments=False, days_to_renewal=None)
    periods: dict[tuple, Decimal] = defaultdict(Decimal)
    for e in lines:
        periods[(e.start_date, e.end_date)] += e.quantity
    paid = {p: q for p, q in periods.items() if q > 0}  # credit memos cancel invoice lines of the same period
    current = {p: q for p, q in paid.items() if (p[0] or dt.date.min) <= today <= p[1]}
    future = {p: q for p, q in paid.items() if (p[0] or dt.date.min) > today}
    if current:
        shown = current
    elif future:
        first = min(p[0] for p in future)
        shown = {p: q for p, q in future.items() if p[0] == first}
    elif paid:
        last = max(p[1] for p in paid)
        shown = {p: q for p, q in paid.items() if p[1] == last}
    else:
        shown = {}
    renewal = max((p[1] for p in paid), default=None)
    days = (renewal - today).days if renewal else None
    last_period = max(paid, key=lambda p: p[1]) if paid else None
    installments = bool(last_period and last_period[0] and (last_period[1] - last_period[0]).days < INSTALMENT_DAYS)
    from_reports = all(e.source == "bmc_mzd" for e in lines)
    if not paid:
        status = "cancelled"
    elif renewal < today:
        status = "awaiting_report" if from_reports and (report_cutoff is None or renewal >= report_cutoff) else "lapsed"
    elif not current and future:
        status = "upcoming"
    elif days <= notice_days and not installments:
        status = "renewal_due"
    else:
        status = "active"
    return Holding(
        **common, quantity=sum(shown.values(), Decimal(0)),
        period_start=min((p[0] for p in shown if p[0]), default=None), period_end=max((p[1] for p in shown), default=None),
        renewal_date=renewal, status=status, installments=installments, days_to_renewal=days)


def holdings(db: Session, account_ids: list[int] | None = None, today: dt.date | None = None) -> list[Holding]:
    today = today or dt.date.today()
    stmt = select(Entitlement)
    if account_ids is not None:
        stmt = stmt.where(Entitlement.account_id.in_(account_ids))
    groups: dict[tuple, list[Entitlement]] = defaultdict(list)
    for e in db.scalars(stmt):
        # a perpetual licence and the support/term lines of the same product are separate holdings
        kind = "perpetual" if e.license_type == "perpetual" else "renewable"
        groups[(e.account_id, e.product_name.lower(), kind)].append(e)
    days = get_settings().renewal_notice_days
    cutoff = db.scalar(select(func.max(Entitlement.document_date)).where(Entitlement.source == "bmc_mzd"))
    out = [_holding(lines, today, days, cutoff) for lines in groups.values()]
    return sorted(out, key=lambda h: (h.account_name.lower(), h.renewal_date or dt.date.max, h.product_name))


# ---------------------------------------------------------------- report import
@dataclass
class ImportResult:
    dry_run: bool
    report: str
    source: str = "pdf"
    reliable: bool = True  # False: problems reading the report, it can only be dry-run
    lines: int = 0
    created: int = 0
    already_imported: int = 0
    fees_filled: int = 0  # already-imported lines that got their Sentry fee from this report
    countries_filled: int = 0  # already-imported lines that got their Sold To Country from this report
    lapsed_closed: int = 0  # lapsed licences this report shows were renewed
    accounts_matched: dict = field(default_factory=dict)   # report name -> CRM account name
    accounts_created: list = field(default_factory=list)
    resellers: dict = field(default_factory=dict)
    totals_checked: int = 0
    warnings: list = field(default_factory=list)
    preview: list = field(default_factory=list)


class AccountMatcher:
    def __init__(self, db: Session):
        self.db = db
        self.by_norm: dict[str, Account] = {}
        for a in db.scalars(select(Account).order_by(Account.id)):
            self.by_norm.setdefault(norm_name(a.name), a)

    def find(self, name: str) -> Account | None:
        key = norm_name(name)
        if not key:
            return None
        if key in self.by_norm:
            return self.by_norm[key]
        # "BMC Software, Inc." vs "BMC Software (BMC Helix)": accept a unique whole-word prefix match
        hits = {id(a): a for k, a in self.by_norm.items()
                if len(key.split()) >= 2 and (k.startswith(key + " ") or key.startswith(k + " ")) and len(k.split()) >= 2}
        return next(iter(hits.values())) if len(hits) == 1 else None

    def get_or_create(self, name: str, country: str | None, account_type: str) -> tuple[Account, bool]:
        a = self.find(name)
        if a:
            return a, False
        a = Account(name=name.strip()[:255], country=(country or "")[:80] or None, account_type=account_type, extra={})
        self.db.add(a)
        self.db.flush()
        self.by_norm[norm_name(name)] = a
        return a, True


def _fill_country(db: Session, account_id: int, country: str) -> None:
    acc = db.get(Account, account_id)
    if acc and not acc.country:
        acc.country = country[:80]


def import_report(db: Session, report: Report, report_name: str, *, dry_run: bool = True) -> ImportResult:
    res = ImportResult(dry_run=dry_run, report=report.title or report_name, source=report.source,
                       reliable=report.reliable, lines=len(report.lines),
                       totals_checked=report.checked_totals, warnings=list(report.warnings))
    brand = db.scalar(select(Brand).where(Brand.code == "SENTRY"))
    existing = set(db.scalars(select(Entitlement.line_key).where(Entitlement.line_key.is_not(None))))
    # lines imported before the fee and the country were stored get them from a re-import of the same report
    incomplete = {e.line_key: e for e in db.scalars(select(Entitlement).where(
        Entitlement.source == "bmc_mzd", Entitlement.line_key.is_not(None),
        (Entitlement.fee_amount.is_(None)) | (Entitlement.country.is_(None))))}
    matcher = AccountMatcher(db)
    seen: dict[str, int] = {}
    for ln in report.lines:
        # a report can hold identical lines (same invoice, product, period, quantity, amount): number the repeats,
        # so they all count, yet the PDF and the .xlsx of one quarter still recognise each other
        seen[ln.key] = seen.get(ln.key, 0) + 1
        key = ln.key if seen[ln.key] == 1 else f"{ln.key}|{seen[ln.key]}"
        if key not in existing:
            # a line read before the "Rev " product-name fix: rename it instead of adding a second copy
            legacy = key.replace(f"|{ln.product.lower()}|", f"|rev {ln.product.lower()}|", 1)
            if legacy in existing and (old := db.scalar(select(Entitlement).where(Entitlement.line_key == legacy))):
                old.product_name, old.line_key = ln.product, key
                existing.discard(legacy)
                existing.add(key)
                incomplete.pop(legacy, None) and incomplete.setdefault(key, old)
        if key in existing:
            res.already_imported += 1
            if (old := incomplete.get(key)) is not None:
                if old.fee_amount is None:
                    old.fee_amount = ln.fee
                    res.fees_filled += 1
                if old.country is None and ln.country:
                    old.country = ln.country[:80]
                    res.countries_filled += 1
                    _fill_country(db, old.account_id, ln.country)
            continue
        existing.add(key)
        acc, created = matcher.get_or_create(ln.customer, ln.country, "customer")
        if created:
            res.accounts_created.append(ln.customer)
        elif norm_name(acc.name) != norm_name(ln.customer) or acc.name != ln.customer:
            res.accounts_matched[ln.customer] = acc.name
        if acc.account_type == "prospect":
            acc.account_type = "customer"
        if not acc.country and ln.country:  # an existing account without a country takes the report's
            acc.country = ln.country[:80]
        reseller = None
        if ln.billing_company and norm_name(ln.billing_company) != norm_name(ln.customer):
            reseller, r_created = matcher.get_or_create(ln.billing_company, ln.country, "reseller")
            res.resellers.setdefault(ln.billing_company, reseller.name + (" (new)" if r_created else ""))
        db.add(Entitlement(
            account_id=acc.id, reseller_id=reseller.id if reseller else None, brand_id=brand.id,
            product_name=ln.product, quantity=ln.quantity,
            license_type=ln.license_type, start_date=ln.start, end_date=ln.end, net_amount=ln.net, fee_amount=ln.fee,
            currency="USD", country=(ln.country or None) and ln.country[:80],
            source="bmc_mzd", source_ref=ln.doc_number, document_date=ln.doc_date, report_name=report_name,
            line_key=key))
        res.created += 1
        if len(res.preview) < 200:
            res.preview.append({"customer": ln.customer, "account": acc.name, "product": ln.product,
                                "type": ln.license_type, "quantity": str(ln.quantity), "start": ln.start,
                                "end": ln.end, "reseller": reseller.name if reseller else None,
                                "document": ln.doc_number})
    res.accounts_created = sorted(set(res.accounts_created))
    db.flush()
    res.lapsed_closed = auto_close_lapsed(db)
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return res


# ---------------------------------------------------------------- renewal notices
def _recipients(db: Session, account: Account) -> list[User]:
    """Owner of the open renewal opportunity for the account, else the account owner, else the administrators."""
    opp = db.scalar(select(Opportunity).join(Stage, Opportunity.stage_id == Stage.id)
                    .join(Pipeline, Opportunity.pipeline_id == Pipeline.id)
                    .where(Opportunity.account_id == account.id, Stage.kind == "open", Pipeline.kind == "renewal",
                           Opportunity.owner_id.is_not(None))
                    .order_by(Opportunity.expected_close_date.asc().nulls_last()))
    if opp and opp.owner and opp.owner.is_active:
        return [opp.owner]
    if account.owner and account.owner.is_active:
        return [account.owner]
    return list(db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True))))


def send_renewal_notices(db: Session, today: dt.date | None = None) -> int:
    """Notify once per licence when its renewal date comes within CRM_RENEWAL_NOTICE_DAYS. Returns notices sent."""
    today = today or dt.date.today()
    due = [h for h in holdings(db, today=today) if h.status == "renewal_due"]
    by_account: dict[int, list[Holding]] = defaultdict(list)
    for h in due:
        line = db.get(Entitlement, h.latest_line_id)
        if line.renewal_notified_at is None:
            by_account[h.account_id].append(h)
    sent = 0
    for account_id, items in by_account.items():
        account = db.get(Account, account_id)
        first = min(h.renewal_date for h in items)
        title = f"{account.name}: licence renewal due {first:%d %b %Y}"
        body = "\n".join(f"- {h.product_name}: {h.quantity.normalize():f} ({h.license_type}), renewal "
                         f"{h.renewal_date:%d %b %Y}" + (f" via {h.reseller}" if h.reseller else "") for h in items)
        for user in _recipients(db, account):
            db.add(Notification(user_id=user.id, kind="renewal_due", title=title, body=body,
                                link=f"/accounts/{account_id}"))
            if mail.status()["enabled"]:
                try:
                    url = f"{get_settings().app_url}/accounts/{account_id}"
                    html = (f"<p>These licences of <b>{_esc(account.name)}</b> are due for renewal:</p><ul>"
                            + "".join(f"<li>{_esc(line[2:])}</li>" for line in body.splitlines())
                            + f'</ul><p><a href="{url}">Open the account in the CRM</a></p>')
                    mail.send(mail.Message(sender=mail.sender_for(user.email), to=[user.email], subject=title,
                                           html=html))
                except mail.MailError:
                    pass  # the in-app notification is the record; email is best effort
        now = dt.datetime.now(dt.UTC)
        for h in items:
            db.get(Entitlement, h.latest_line_id).renewal_notified_at = now
        sent += 1
    db.commit()
    return sent


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def lapsed(db: Session, include_resolved: bool = False) -> list[Holding]:
    out = [h for h in holdings(db) if h.status == "lapsed" and (include_resolved or not h.resolved)]
    # did the customer buy anything after it ended (often a bundle replacing single products)?
    later: dict[int, list[Entitlement]] = defaultdict(list)
    for e in db.scalars(select(Entitlement).where(Entitlement.account_id.in_({h.account_id for h in out}),
                                                   Entitlement.quantity > 0)):
        later[e.account_id].append(e)
    for h in out:
        mine = set(h.lines)
        after = [e for e in later[h.account_id] if e.id not in mine and (
            (e.end_date and e.end_date > h.renewal_date) or (e.start_date and e.start_date > h.renewal_date))]
        if after:
            r = max(after, key=lambda e: (e.end_date or e.start_date, e.id))
            h.later_purchase = {"product": r.product_name, "start": r.start_date, "end": r.end_date,
                                "products": len({e.product_name for e in after})}
    return out


def resolve(db: Session, line_ids: list[int], user_id: int | None, note: str | None) -> int:
    """Mark lapsed licences resolved by the latest line of each (as the dashboard lists them)."""
    now = dt.datetime.now(dt.UTC)
    n = 0
    for e in db.scalars(select(Entitlement).where(Entitlement.id.in_(line_ids))):
        e.lapse_resolved_at, e.lapse_resolved_by_id, e.lapse_resolution = now, user_id, (note or "").strip() or None
        n += 1
    return n


def auto_close_lapsed(db: Session, today: dt.date | None = None) -> int:
    """Close lapsed licences that were renewed after all: any imported line (any report, or added by hand) for the
    same customer and product family with dates after the lapsed renewal date. TrueSight, BMC Helix and OnPrem names
    of one product count as the same. Returns how many were closed; the caller commits."""
    from .product_families import family

    open_lapses = [h for h in holdings(db, today=today) if h.status == "lapsed" and not h.resolved]
    if not open_lapses:
        return 0
    later: dict[tuple[int, str], list[Entitlement]] = defaultdict(list)
    for e in db.scalars(select(Entitlement).where(Entitlement.account_id.in_({h.account_id for h in open_lapses}),
                                                   Entitlement.quantity > 0)):
        later[(e.account_id, family(e.product_name))].append(e)
    now = dt.datetime.now(dt.UTC)
    closed = 0
    for h in open_lapses:
        mine = set(h.lines)
        renewals = [e for e in later[(h.account_id, family(h.product_name))] if e.id not in mine and (
            (e.end_date and e.end_date > h.renewal_date) or (e.start_date and e.start_date > h.renewal_date))]
        if not renewals:
            continue
        r = max(renewals, key=lambda e: (e.end_date or e.start_date, e.id))
        where = (r.report_name or "").replace("\\", "/").rsplit("/", 1)[-1] or ("added by hand" if r.source == "manual"
                                                                            else r.source)
        period = f"{r.start_date:%d %b %Y} – {r.end_date:%d %b %Y}" if r.start_date and r.end_date else \
            f"from {(r.start_date or r.end_date):%d %b %Y}"
        line = db.get(Entitlement, h.latest_line_id)
        line.lapse_resolved_at, line.lapse_resolved_by_id = now, None
        line.lapse_resolution = (f"Closed automatically: renewed as {r.product_name}, {period}"
                                 f" ({where}{', ' + r.source_ref if r.source_ref else ''})")[:2000]
        closed += 1
    db.flush()
    return closed


def account_summary(db: Session, account_ids: list[int]) -> dict[int, dict]:
    """Compact per-account licence summary for search results."""
    out: dict[int, dict] = {}
    for h in holdings(db, account_ids):
        if h.status == "cancelled":
            continue
        s = out.setdefault(h.account_id, {"products": [], "next_renewal": None, "lapsed": 0})
        s["products"].append({"product": h.product_name, "quantity": h.quantity, "renewal_date": h.renewal_date,
                              "status": h.status})
        if h.status == "lapsed":
            s["lapsed"] += 1
        elif h.renewal_date and (s["next_renewal"] is None or h.renewal_date < s["next_renewal"]):
            s["next_renewal"] = h.renewal_date
    return out


"""Business logic shared by routers, imports and (later) inbound webhooks."""
import calendar
import datetime as dt
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Account,
    Activity,
    Brand,
    CampaignRecipient,
    Contact,
    FormSubmission,
    ListMember,
    LineItem,
    Opportunity,
    Pipeline,
    PriceBook,
    PriceBookEntry,
    Product,
    Stage,
    StageHistory,
    User,
    WebEvent,
    WebVisitor,
)
from .pricing import compute_totals, months_between
from .schemas import LineItemIn

FREE_EMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "yahoo.fr", "hotmail.com", "hotmail.fr", "outlook.com",
    "outlook.fr", "live.com", "msn.com", "icloud.com", "me.com", "aol.com", "proton.me", "protonmail.com",
    "gmx.com", "gmx.de", "web.de", "orange.fr", "free.fr", "wanadoo.fr", "laposte.net", "sfr.fr",
    "yandex.com", "mail.com", "zoho.com", "qq.com", "163.com", "rediffmail.com",
}


def add_months(d: dt.date, months: int) -> dt.date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    domain = email.rsplit("@", 1)[1].strip().lower()
    return None if domain in FREE_EMAIL_DOMAINS else domain


def find_contact_by_email(db: Session, email: str | None) -> Contact | None:
    if not email:
        return None
    return db.scalar(select(Contact).where(func.lower(Contact.email) == email.strip().lower()))


MERGE_FIELDS = ("first_name", "last_name", "phone", "mobile", "job_title", "account_id", "source", "brand_id",
                "owner_id", "country", "linkedin", "consent_at")


def merge_contacts(db: Session, keep: Contact, drop: Contact) -> None:
    """Merge `drop` into `keep` and delete it: its timeline, deals, list memberships, campaign history and form
    submissions move over, and blank fields of `keep` are filled from `drop`. `keep`'s email address stays;
    `drop`'s is remembered in extra.previous_emails."""
    if keep.id == drop.id:
        return
    for f in MERGE_FIELDS:
        if getattr(keep, f) in (None, "") and getattr(drop, f) not in (None, ""):
            setattr(keep, f, getattr(drop, f))
    keep.consent_marketing = keep.consent_marketing or drop.consent_marketing
    keep.unsubscribed = keep.unsubscribed or drop.unsubscribed  # an opt-out always wins
    keep.notes = "\n\n".join(n for n in (keep.notes, drop.notes) if n) or None
    extra = {**(drop.extra or {}), **(keep.extra or {})}
    prev = list(dict.fromkeys([*(keep.extra or {}).get("previous_emails", []), *(drop.extra or {}).get(
        "previous_emails", []), *([drop.email.lower()] if drop.email else [])]))
    if prev:
        extra["previous_emails"] = [e for e in prev if e != (keep.email or "").lower()]
    keep.extra = extra
    if not keep.external_id and drop.external_id:  # unique together: free it on drop first
        ref = (drop.external_source, drop.external_id)
        drop.external_source = drop.external_id = None
        db.flush()
        keep.external_source, keep.external_id = ref
    db.query(Activity).filter(Activity.contact_id == drop.id).update({"contact_id": keep.id})
    db.query(Opportunity).filter(Opportunity.primary_contact_id == drop.id).update({"primary_contact_id": keep.id})
    db.query(Opportunity).filter(Opportunity.partner_contact_id == drop.id).update({"partner_contact_id": keep.id})
    db.query(FormSubmission).filter(FormSubmission.contact_id == drop.id).update({"contact_id": keep.id})
    db.query(WebVisitor).filter(WebVisitor.contact_id == drop.id).update({"contact_id": keep.id})
    db.query(WebEvent).filter(WebEvent.contact_id == drop.id).update({"contact_id": keep.id})
    # memberships and campaign rows are unique per contact: move those keep doesn't already have
    lists = set(db.scalars(select(ListMember.list_id).where(ListMember.contact_id == keep.id)))
    for m in db.scalars(select(ListMember).where(ListMember.contact_id == drop.id)).all():
        if m.list_id in lists:
            if m.status == "unsubscribed":  # the person opted out of this list under the other address
                db.query(ListMember).filter(ListMember.list_id == m.list_id, ListMember.contact_id == keep.id).update(
                    {"status": "unsubscribed", "unsubscribed_at": m.unsubscribed_at})
            db.delete(m)
        else:
            m.contact_id = keep.id
    sent = set(db.scalars(select(CampaignRecipient.campaign_id).where(CampaignRecipient.contact_id == keep.id)))
    for r in db.scalars(select(CampaignRecipient).where(CampaignRecipient.contact_id == drop.id)).all():
        if r.campaign_id in sent:
            r.contact_id = None  # keeps the campaign report's counts
        else:
            r.contact_id = keep.id
    db.flush()
    db.delete(drop)
    db.flush()


def find_or_create_account(db: Session, name: str | None, domain: str | None, **defaults) -> Account | None:
    """Match by domain first, then case-insensitive name; create if neither matches and a name is given."""
    if domain:
        acc = db.scalar(select(Account).where(Account.domain == domain.lower()).order_by(Account.id))
        if acc:
            return acc
    if name:
        acc = db.scalar(select(Account).where(func.lower(Account.name) == name.strip().lower()).order_by(Account.id))
        if acc:
            if domain and not acc.domain:
                acc.domain = domain.lower()
            return acc
    if not name and domain:
        name = domain.split(".")[0].capitalize()
    if not name:
        return None
    acc = Account(name=name.strip(), domain=domain.lower() if domain else None, extra={}, **defaults)
    db.add(acc)
    db.flush()
    return acc


# ---------------- Opportunities ----------------
def default_pipeline(db: Session, kind: str = "new_business") -> Pipeline:
    p = db.scalar(select(Pipeline).where(Pipeline.kind == kind).order_by(Pipeline.id))
    if not p:
        raise HTTPException(500, f"No pipeline of kind {kind} configured")
    return p


def default_price_book(db: Session, brand_id: int) -> PriceBook | None:
    return db.scalar(
        select(PriceBook)
        .where(PriceBook.active.is_(True), PriceBook.brand_id == brand_id)
        .order_by(PriceBook.is_default.desc(), PriceBook.id)
    )


def sync_contract_dates(opp: Opportunity) -> None:
    """Keep contract start/end and term consistent."""
    if opp.contract_start and opp.contract_end:
        if opp.contract_end < opp.contract_start:
            raise HTTPException(422, "Contract end date is before start date")
        opp.term_months = max(months_between(opp.contract_start, opp.contract_end), 1)
    elif opp.contract_start and opp.term_months:
        opp.contract_end = add_months(opp.contract_start, opp.term_months) - dt.timedelta(days=1)


def set_line_items(db: Session, opp: Opportunity, items: list[LineItemIn]) -> None:
    opp.line_items.clear()
    db.flush()
    for pos, item in enumerate(items):
        product = db.get(Product, item.product_id) if item.product_id else None
        if item.product_id and not product:
            raise HTTPException(422, f"Product {item.product_id} not found")
        unit_price = item.unit_price
        if unit_price is None:
            if not product:
                raise HTTPException(422, "unit_price is required for custom lines")
            entry = None
            if opp.price_book_id:
                entry = db.scalar(select(PriceBookEntry).where(
                    PriceBookEntry.price_book_id == opp.price_book_id, PriceBookEntry.product_id == product.id))
            if not entry:
                raise HTTPException(422, f"No price for {product.sku} in the selected price book")
            unit_price = entry.unit_price
        name = item.name or (product.name if product else None)
        if not name:
            raise HTTPException(422, "Line name is required for custom lines")
        opp.line_items.append(LineItem(
            product_id=product.id if product else None,
            position=pos,
            name=name,
            description=item.description,
            unit=product.unit if product else item.unit,
            billing_type=item.billing_type or (product.billing_type if product else "recurring"),
            quantity=item.quantity,
            unit_price=unit_price,
            discount_pct=item.discount_pct,
            term_months=item.term_months,
            fixed_total=item.fixed_total,
        ))
    recompute(opp)


def recompute(opp: Opportunity) -> None:
    totals = compute_totals(opp.line_items, opp.term_months)
    opp.amount_tcv = totals.tcv
    opp.amount_arr = totals.arr


def validate_stage(db: Session, opp: Opportunity, stage_id: int) -> Stage:
    stage = db.get(Stage, stage_id)
    if not stage:
        raise HTTPException(422, "Stage not found")
    return stage


def change_stage(db: Session, opp: Opportunity, stage: Stage, user: User | None, lost_reason: str | None = None):
    if opp.stage_id == stage.id:
        return
    db.add(StageHistory(opportunity_id=opp.id, from_stage_id=opp.stage_id, to_stage_id=stage.id,
                        changed_by_id=user.id if user else None))
    opp.stage_id = stage.id
    opp.pipeline_id = stage.pipeline_id
    opp.stage = stage
    if lost_reason:
        opp.lost_reason = lost_reason
    if stage.kind in ("won", "lost"):
        opp.closed_at = dt.datetime.now(dt.UTC)
    else:
        opp.closed_at = None
    if stage.kind == "won":
        on_won(db, opp)


def on_won(db: Session, opp: Opportunity) -> None:
    account = db.get(Account, opp.account_id)
    if account and account.account_type == "prospect":
        account.account_type = "customer"
    if opp.primary_contact_id:
        c = db.get(Contact, opp.primary_contact_id)
        if c and c.lifecycle in ("lead", "qualified"):
            c.lifecycle = "customer"


def brand_exists(db: Session, brand_id: int) -> None:
    if not db.get(Brand, brand_id):
        raise HTTPException(422, f"Brand {brand_id} not found")


def money(v) -> Decimal:
    return Decimal(v or 0).quantize(Decimal("0.01"))

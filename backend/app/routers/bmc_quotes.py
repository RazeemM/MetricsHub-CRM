"""BMC quotes: paste a quote approval email and get a Sentry opportunity with its Sentry product lines."""
import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import bmc_quote
from ..crud import get_or_404
from ..db import get_db
from ..enums import DealType
from ..models import Account, Activity, Brand, Contact, Opportunity, PriceBook, Stage, User
from ..schemas import LineItemIn, OpportunityCreate, OpportunityOut
from ..security import require_writer
from ..services import default_pipeline
from .opportunities import _load, create_opportunity

router = APIRouter(prefix="/api/opportunities/bmc-quote", tags=["opportunities"])

SOURCE = "bmc_quote"


class QuoteText(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)


class QuoteImport(QuoteText):
    account_id: int
    title: str | None = Field(default=None, max_length=255)
    deal_type: DealType = DealType.new
    stage_id: int | None = None
    owner_id: int | None = None
    expected_close_date: dt.date | None = None
    skip: list[int] = []  # positions in the preview's Sentry lines to leave out


def _parse(text: str) -> bmc_quote.ParsedQuote:
    try:
        q = bmc_quote.parse(text)
    except bmc_quote.QuoteError as e:
        raise HTTPException(422, str(e)) from None
    if not q.sentry_lines:
        raise HTTPException(422, f"The quote has {len(q.lines)} product lines but none of them is a Sentry product.")
    return q


def _bmc(db: Session) -> Account | None:
    return db.scalar(select(Account).where(Account.account_type == "platform_partner", or_(
        Account.domain == "bmc.com", Account.name.ilike("BMC%"))).order_by(Account.id))


def _contact(db: Session, name: str | None) -> Contact | None:
    if not name:
        return None
    full = func.lower(func.concat(func.coalesce(Contact.first_name, ""), " ", func.coalesce(Contact.last_name, "")))
    return db.scalar(select(Contact).where(full == name.strip().lower()).order_by(Contact.id))


def _account(db: Session, name: str | None) -> Account | None:
    if not name:
        return None
    return db.scalar(select(Account).where(func.lower(Account.name) == name.strip().lower()).order_by(Account.id))


def _existing(db: Session, q: bmc_quote.ParsedQuote) -> Opportunity | None:
    return db.scalar(select(Opportunity).where(Opportunity.external_source == SOURCE,
                                               Opportunity.external_id == q.fingerprint()))


def _deal_type(q: bmc_quote.ParsedQuote) -> str:
    return "renewal" if all("renew" in ln.action.lower() for ln in q.sentry_lines) else "new"


def _stage(db: Session, deal_type: str) -> Stage:
    """The quote is being approved: the proposal stage of new business, "Renewal pending" for renewals."""
    pipeline = default_pipeline(db, "renewal" if deal_type == "renewal" else "new_business")
    word = "pending" if deal_type == "renewal" else "proposal"
    return next((s for s in pipeline.stages if s.kind == "open" and word in s.name.lower()), pipeline.stages[0])


def _money(cur: str, value: Decimal) -> str:
    return f"{cur} {value:,.2f}"


@router.post("/preview")
def preview(data: QuoteText, db: Session = Depends(get_db), _: User = Depends(require_writer)):
    """What an import of this quote would create, for the user to check first."""
    q = _parse(data.text)
    sentry = q.sentry_lines
    rep = _contact(db, q.sales_rep)
    account = _account(db, q.customer)
    existing = _existing(db, q)
    deal_type = _deal_type(q)
    return {
        "quote_number": q.quote_number,
        "customer": q.customer,
        "account": {"id": account.id, "name": account.name} if account else None,
        "currency": q.currency,
        "line_count": len(q.lines),
        "quote_total": sum((ln.total_charge for ln in q.lines), Decimal(0)),
        "sentry_total": sum((ln.total_charge for ln in sentry), Decimal(0)),
        "contract_start": min(ln.start for ln in sentry),
        "contract_end": max(ln.end for ln in sentry),
        "deal_type": deal_type,
        "stage_id": _stage(db, deal_type).id,
        "sales_rep": {"name": q.sales_rep, "contact_id": rep.id if rep else None} if q.sales_rep else None,
        "approvals": [a.__dict__ for a in q.approvals],
        "existing": {"id": existing.id, "title": existing.title} if existing else None,
        "lines": [{
            "name": ln.name, "quantity": ln.quantity, "start": ln.start, "end": ln.end, "term_months": ln.term_months,
            "total_charge": ln.total_charge, "discount_pct": ln.discount_pct, "list_price": ln.list_price,
            "effective_price": ln.effective_price, "status": ln.status, "action": ln.action,
            "revenue_type": ln.revenue_type,
        } for ln in sentry],
    }


@router.post("", response_model=OpportunityOut, status_code=201)
def import_quote(data: QuoteImport, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Create a Sentry opportunity from the Sentry lines of a BMC quote, sold through BMC MarketZone."""
    q = _parse(data.text)
    lines = [ln for i, ln in enumerate(q.sentry_lines) if i not in set(data.skip)]
    if not lines:
        raise HTTPException(422, "Keep at least one Sentry product line")
    if existing := _existing(db, q):
        raise HTTPException(409, f"This quote was already imported as opportunity #{existing.id} "
                                 f"\"{existing.title}\"")
    account = get_or_404(db, Account, data.account_id)
    brand = db.scalar(select(Brand).where(Brand.code == "SENTRY"))
    if not brand:
        raise HTTPException(422, "There is no Sentry brand")
    if data.stage_id:
        stage = get_or_404(db, Stage, data.stage_id)
    else:
        stage = _stage(db, data.deal_type)
    book = db.scalar(select(PriceBook).where(PriceBook.brand_id == brand.id, PriceBook.active.is_(True),
                                             PriceBook.currency == q.currency)
                     .order_by(PriceBook.is_default.desc(), PriceBook.id))
    platform, rep = _bmc(db), _contact(db, q.sales_rep)
    cur = q.currency
    start, end = min(ln.start for ln in lines), max(ln.end for ln in lines)
    total = sum((ln.total_charge for ln in lines), Decimal(0))
    number = f" {q.quote_number}" if q.quote_number else ""
    summary = [
        f"Created from BMC quote{number} on {dt.date.today():%d %b %Y} by {user.full_name}.",
        f"Sentry products: {len(lines)} of the quote's {len(q.lines)} lines, {_money(cur, total)} of "
        f"{_money(cur, sum((ln.total_charge for ln in q.lines), Decimal(0)))} (total charges).",
    ]
    if q.sales_rep:
        summary.append(f"BMC sales rep: {q.sales_rep}.")
    opp = create_opportunity(OpportunityCreate(
        title=data.title or f"{account.name} - Sentry via BMC{number}",
        account_id=account.id, brand_id=brand.id, owner_id=data.owner_id, stage_id=stage.id,
        deal_type=data.deal_type, lead_source="platform_referral", route_to_market="bmc_marketzone",
        referring_platform_id=platform.id if platform else None, partner_contact_id=rep.id if rep else None,
        price_book_id=book.id if book else None, currency=cur, contract_start=start, contract_end=end,
        expected_close_date=data.expected_close_date or start, description="\n".join(summary),
        line_items=[LineItemIn(name=ln.name[:200], description=ln.description(), quantity=1,
                               unit_price=ln.total_charge, billing_type="recurring", unit="deal_total",
                               term_months=ln.term_months) for ln in lines],
    ), db, user)

    row = db.get(Opportunity, opp.id)
    row.external_source, row.external_id = SOURCE, q.fingerprint()
    body = ["Sentry lines:"] + [f"- {ln.name}: {_money(cur, ln.total_charge)} ({ln.description()})" for ln in lines]
    if q.approvals:
        body += ["", "Approvals:"] + [f"- {a.step}: {a.status} {a.date}, {a.assigned_to}" for a in q.approvals]
    db.add(Activity(type="note", subject=f"BMC quote{number} imported", body="\n".join(body),
                    owner_id=row.owner_id, created_by_id=user.id, account_id=account.id, opportunity_id=row.id,
                    completed_at=dt.datetime.now(dt.UTC)))
    db.commit()
    return _load(db, opp.id)

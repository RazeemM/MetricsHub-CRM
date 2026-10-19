import datetime as dt
from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from ..db import get_db
from ..entitlements import holdings
from ..models import Account, Activity, Brand, Contact, Entitlement, Opportunity, Stage, User
from ..regions import REGIONS, region_of
from ..security import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def summary(brand_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    def scoped(stmt):
        return stmt.where(Opportunity.brand_id == brand_id) if brand_id else stmt

    open_q = scoped(select(Opportunity).join(Stage, Opportunity.stage_id == Stage.id).where(Stage.kind == "open"))
    open_opps = db.scalars(open_q).all()
    # Amounts are never summed across currencies
    pipeline: dict[str, dict] = {}
    for o in open_opps:
        cur = pipeline.setdefault(o.currency, {"total": Decimal(0), "weighted": Decimal(0), "count": 0})
        cur["total"] += o.amount_tcv
        cur["weighted"] += o.weighted_amount
        cur["count"] += 1

    today = dt.date.today()
    q_start = dt.date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    won_q = scoped(select(Opportunity.currency, func.count(), func.coalesce(func.sum(Opportunity.amount_tcv), 0))
                   .join(Stage, Opportunity.stage_id == Stage.id)
                   .where(Stage.kind == "won", Opportunity.closed_at >= q_start).group_by(Opportunity.currency))
    won = [{"currency": c, "count": n, "amount": a} for c, n, a in db.execute(won_q).all()]
    closed_q = scoped(select(Stage.kind, func.count()).join(Opportunity, Opportunity.stage_id == Stage.id)
                      .where(Stage.kind.in_(["won", "lost"]),
                             Opportunity.closed_at >= today - dt.timedelta(days=365)).group_by(Stage.kind))
    closed = dict(db.execute(closed_q).all())
    win_rate = round(100 * closed.get("won", 0) / max(closed.get("won", 0) + closed.get("lost", 0), 1))

    by_stage = db.execute(scoped(
        select(Stage.name, Opportunity.currency, func.count(Opportunity.id),
               func.coalesce(func.sum(Opportunity.amount_tcv), 0))
        .join(Opportunity, Opportunity.stage_id == Stage.id).where(Stage.kind == "open")
        .group_by(Stage.id, Stage.name, Stage.position, Stage.pipeline_id, Opportunity.currency)
        .order_by(Stage.pipeline_id, Stage.position))).all()

    platform = aliased(Account)
    by_platform = db.execute(scoped(
        select(func.coalesce(platform.name, "Direct / none"), Opportunity.currency, func.count(Opportunity.id),
               func.coalesce(func.sum(Opportunity.amount_tcv), 0))
        .join(Stage, Opportunity.stage_id == Stage.id)
        .outerjoin(platform, Opportunity.referring_platform_id == platform.id)
        .where(Stage.kind == "open").group_by(platform.name, Opportunity.currency)
        .order_by(func.sum(Opportunity.amount_tcv).desc()))).all()

    by_brand = db.execute(
        select(Brand.name, Opportunity.currency, func.count(Opportunity.id),
               func.coalesce(func.sum(Opportunity.amount_tcv), 0))
        .join(Opportunity, Opportunity.brand_id == Brand.id).join(Stage, Opportunity.stage_id == Stage.id)
        .where(Stage.kind == "open").group_by(Brand.name, Opportunity.currency)).all()

    closing_soon = scoped(select(Opportunity).join(Stage, Opportunity.stage_id == Stage.id).where(
        Stage.kind == "open", Opportunity.expected_close_date <= today + dt.timedelta(days=30))
        .order_by(Opportunity.expected_close_date).limit(10))

    my_tasks = db.scalars(select(Activity).where(Activity.type == "task", Activity.completed_at.is_(None),
                                                 Activity.owner_id == user.id)
                          .order_by(Activity.due_at.asc().nulls_last()).limit(10)).all()
    new_leads = db.scalar(select(func.count()).select_from(Contact).where(
        Contact.lifecycle == "lead", Contact.created_at >= today - dt.timedelta(days=30)))

    return {
        "open_count": len(open_opps),
        "pipeline": [{"currency": c, **v} for c, v in sorted(pipeline.items())],
        "won_this_quarter": won,
        "win_rate_12m": win_rate,
        "new_leads_30d": new_leads,
        "by_stage": [{"stage": n, "currency": cur, "count": c, "amount": a} for n, cur, c, a in by_stage],
        "by_platform": [{"platform": n, "currency": cur, "count": c, "amount": a} for n, cur, c, a in by_platform],
        "by_brand": [{"brand": n, "currency": cur, "count": c, "amount": a} for n, cur, c, a in by_brand],
        "closing_soon": [{"id": o.id, "title": o.title, "amount": o.amount_tcv, "currency": o.currency,
                          "expected_close_date": o.expected_close_date, "stage": o.stage.name}
                         for o in db.scalars(closing_soon)],
        "my_tasks": [{"id": t.id, "subject": t.subject, "due_at": t.due_at, "contact_id": t.contact_id,
                      "account_id": t.account_id, "opportunity_id": t.opportunity_id} for t in my_tasks],
    }


# ---------------- licences (BMC MarketZone reports and licences added by hand) ----------------
HELD = ("active", "renewal_due", "awaiting_report", "upcoming", "perpetual")


def _line_date(e: Entitlement) -> dt.date | None:
    """When a licence line counts for revenue: its invoice date, else its start."""
    return e.document_date or e.start_date


@router.get("/licences")
def licence_analytics(period: str = "all", db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Data for the licence charts. period = "all" or a year ("2026") for the revenue breakdowns."""
    today = dt.date.today()
    rows = db.execute(select(Entitlement, Account.country, Account.region)
                      .join(Account, Entitlement.account_id == Account.id)).all()
    # the report's Sold To Country on each line; the account's country only for licences added by hand
    def line_country(e: Entitlement, account_country: str | None) -> str:
        return ((e.country or account_country or "").strip()) or "Unknown"

    line_region = {e.id: region_of(line_country(e, c), r) for e, c, r in rows}
    country_of_line = {e.id: line_country(e, c) for e, c, _ in rows}
    # an account counts in the region of its most recent licence line
    latest: dict[int, Entitlement] = {}
    for e, _, _ in rows:
        cur = latest.get(e.account_id)
        if cur is None or (_line_date(e) or dt.date.min, e.id) > (_line_date(cur) or dt.date.min, cur.id):
            latest[e.account_id] = e
    region_of_account = {a: line_region[e.id] for a, e in latest.items()}
    year = int(period) if period.isdigit() else None
    in_period = [e for e, _, _ in rows if e.net_amount is not None and _line_date(e)
                 and (year is None or _line_date(e).year == year)]

    # products: customers holding each product now, and revenue in the period
    holders: dict[str, set[int]] = defaultdict(set)
    for h in holdings(db, today=today):
        if h.status in HELD:
            holders[h.product_name].add(h.account_id)
    revenue_by_product: dict[str, Decimal] = defaultdict(Decimal)
    by_region: dict[str, Decimal] = defaultdict(Decimal)
    by_country: dict[str, Decimal] = defaultdict(Decimal)
    for e in in_period:
        revenue_by_product[e.product_name] += e.net_amount
        by_region[line_region[e.id]] += e.net_amount
        by_country[country_of_line[e.id]] += e.net_amount
    names = set(holders) | set(revenue_by_product)
    products = sorted(({"product": n, "customers": len(holders.get(n, ())), "revenue": revenue_by_product.get(n, 0)}
                       for n in names), key=lambda p: (-p["customers"], -p["revenue"], p["product"]))

    # active customers per year and region: a paid licence period overlapping the year
    years3 = [today.year - 2, today.year - 1, today.year]
    qty: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for e, _, _ in rows:
        start = e.start_date or e.document_date
        end = e.end_date or (dt.date(start.year, 12, 31) if start else None)  # perpetual: its purchase year
        if not start or not end:
            continue
        for y in years3:
            if start <= dt.date(y, 12, 31) and end >= dt.date(y, 1, 1):
                qty[(y, e.account_id)] += e.quantity  # credit memos cancel their invoice
    active = {y: defaultdict(int) for y in years3}
    for (y, account_id), q in qty.items():
        if q > 0:
            active[y][region_of_account[account_id]] += 1

    # invoiced (net) and paid to Sentry (fee) per invoice year
    years4 = [today.year - 3, today.year - 2, today.year - 1, today.year]
    money = {y: {"invoiced": Decimal(0), "fee": Decimal(0)} for y in years4}
    missing_fee = 0
    implausible = []  # a fee larger than the amount invoiced is a reporting error (seen: fee = net x quantity)
    for e, _, _ in rows:
        d = _line_date(e)
        if e.net_amount is None or not d or d.year not in money:
            continue
        money[d.year]["invoiced"] += e.net_amount
        if e.fee_amount is None:
            missing_fee += e.source == "bmc_mzd"
        elif e.net_amount > 0 and e.fee_amount > e.net_amount:
            implausible.append({"report": (e.report_name or "").replace("\\", "/").rsplit("/", 1)[-1],
                                "invoice": e.source_ref, "date": d, "account_id": e.account_id,
                                "product": e.product_name, "invoiced": e.net_amount, "fee": e.fee_amount})
        else:
            money[d.year]["fee"] += e.fee_amount

    years_with_data = sorted({_line_date(e).year for e, _, _ in rows if _line_date(e)}, reverse=True)
    return {
        "period": period, "years": years_with_data, "currency": "USD",
        "products": products,
        "revenue_by_region": sorted(({"name": k, "amount": v} for k, v in by_region.items() if v),
                                    key=lambda r: -r["amount"]),
        "revenue_by_country": sorted(({"name": k, "amount": v} for k, v in by_country.items() if v),
                                     key=lambda r: -r["amount"]),
        "regions": [*REGIONS, "Other"],
        "active_customers": [{"year": y, **{r: active[y].get(r, 0) for r in [*REGIONS, "Other"]},
                              "total": sum(active[y].values())} for y in years3],
        "invoiced_vs_fee": [{"year": y, **money[y]} for y in years4],
        "lines_missing_fee": missing_fee,
        "fees_excluded": sorted(implausible, key=lambda x: -x["fee"]),
    }

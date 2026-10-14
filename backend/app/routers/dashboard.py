import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from ..db import get_db
from ..models import Account, Activity, Brand, Contact, Opportunity, Stage, User
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

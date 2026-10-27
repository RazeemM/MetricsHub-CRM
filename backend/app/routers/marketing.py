"""Marketing: dynamic audiences (segments), the marketing overview, and adding contacts to lists in bulk."""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import audiences as aud
from .. import campaigns as cmp
from ..crud import apply_changes, audit, get_or_404, paginate
from ..db import get_db
from ..models import Audience, Campaign, CampaignRecipient, Contact, ListMember, MailingList, User
from ..security import get_current_user, require_writer
from .email import _add, _list_out

router = APIRouter(prefix="/api", tags=["marketing"])


class AudienceIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = None
    brand_id: int | None = None
    rules: aud.AudienceRules = Field(default_factory=aud.AudienceRules)


class AudienceOut(AudienceIn):
    model_config = {"from_attributes": True}
    id: int
    created_at: dt.datetime
    updated_at: dt.datetime
    counts: dict | None = None


def _out(db: Session, a: Audience) -> AudienceOut:
    o = AudienceOut.model_validate(a)
    o.counts = aud.count(db, a.rules)
    return o


def _unique_name(db: Session, model, name: str, exclude_id: int | None = None):
    q = select(model).where(func.lower(model.name) == name.strip().lower())
    if exclude_id:
        q = q.where(model.id != exclude_id)
    if db.scalar(q):
        raise HTTPException(409, "This name is already used")


@router.get("/audiences", response_model=list[AudienceOut])
def list_audiences(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_out(db, a) for a in db.scalars(select(Audience).order_by(Audience.name))]


@router.post("/audiences/preview")
def preview_audience(rules: aud.AudienceRules, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Counts and the first few contacts for rules being edited (nothing saved)."""
    sample = db.scalars(select(Contact).options(selectinload(Contact.account)).where(aud.condition(rules))
                        .order_by(Contact.created_at.desc()).limit(10)).all()
    return {**aud.count(db, rules), "sample": [
        {"id": c.id, "name": c.full_name, "email": c.email, "company": c.account.name if c.account else None}
        for c in sample]}


@router.post("/audiences", response_model=AudienceOut, status_code=201)
def create_audience(data: AudienceIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    _unique_name(db, Audience, data.name)
    a = Audience(name=data.name.strip(), description=data.description, brand_id=data.brand_id,
                 rules=data.rules.model_dump(exclude_defaults=True), created_by_id=user.id)
    db.add(a)
    db.flush()
    audit(db, user, "audience", a.id, "create", {"name": a.name})
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.get("/audiences/{aid}", response_model=AudienceOut)
def get_audience(aid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _out(db, get_or_404(db, Audience, aid))


@router.put("/audiences/{aid}", response_model=AudienceOut)
def update_audience(aid: int, data: AudienceIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    a = get_or_404(db, Audience, aid)
    _unique_name(db, Audience, data.name, exclude_id=a.id)
    data.name = data.name.strip()
    changes = apply_changes(a, data, exclude={"rules"})
    rules = data.rules.model_dump(exclude_defaults=True)
    if rules != a.rules:
        a.rules = rules
        changes["rules"] = rules
    audit(db, user, "audience", a.id, "update", changes)
    db.commit()
    db.refresh(a)
    return _out(db, a)


@router.delete("/audiences/{aid}", status_code=204)
def delete_audience(aid: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    a = get_or_404(db, Audience, aid)
    used = db.scalar(select(Campaign.name).where(Campaign.status.in_(("draft", "scheduled")),
                                                 Campaign.audience_ids.contains([a.id])))
    if used:
        raise HTTPException(409, f"Campaign '{used}' is to be sent to this audience: remove it there first")
    audit(db, user, "audience", a.id, "delete", {"name": a.name})
    db.delete(a)
    db.commit()


@router.get("/audiences/{aid}/contacts")
def audience_contacts(aid: int, q: str | None = None, page: int = Query(1, ge=1),
                      page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                      _: User = Depends(get_current_user)):
    a = get_or_404(db, Audience, aid)
    stmt = select(Contact).options(selectinload(Contact.account)).where(aud.condition(a.rules))
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(Contact.email.ilike(term) | Contact.first_name.ilike(term) | Contact.last_name.ilike(term))
    items, total = paginate(db, stmt.order_by(Contact.last_name, Contact.id), page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": [{
        "id": c.id, "name": c.full_name, "email": c.email, "company": c.account.name if c.account else None,
        "lifecycle": c.lifecycle, "consent": c.consent_marketing, "unsubscribed": c.unsubscribed} for c in items]}


class SaveAsListIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)


@router.post("/audiences/{aid}/save-as-list")
def audience_to_list(aid: int, data: SaveAsListIn, db: Session = Depends(get_db),
                     user: User = Depends(require_writer)):
    """Freeze who matches today into a new static list (e.g. the invitees of an event)."""
    a = get_or_404(db, Audience, aid)
    _unique_name(db, MailingList, data.name)
    ml = MailingList(name=data.name.strip(), kind="list", brand_id=a.brand_id,
                     description=f"Saved from the audience '{a.name}' on {dt.date.today():%d %b %Y}")
    db.add(ml)
    db.flush()
    added = _add(db, ml.id, set(aud.contact_ids(db, a.rules)), "audience")
    audit(db, user, "mailing_list", ml.id, "create", {"name": ml.name, "from_audience": a.id, "added": added})
    db.commit()
    return _list_out(db, ml)


# ---------------- contacts → lists ----------------
class BulkListIn(BaseModel):
    contact_ids: list[int] = Field(min_length=1, max_length=5000)
    list_id: int | None = None
    new_list_name: str | None = Field(default=None, max_length=160)  # create this list and add them to it


@router.post("/contacts/add-to-list")
def add_contacts_to_list(data: BulkListIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    if data.list_id:
        ml = get_or_404(db, MailingList, data.list_id)
    elif data.new_list_name and data.new_list_name.strip():
        _unique_name(db, MailingList, data.new_list_name)
        ml = MailingList(name=data.new_list_name.strip(), kind="list")
        db.add(ml)
        db.flush()
        audit(db, user, "mailing_list", ml.id, "create", {"name": ml.name})
    else:
        raise HTTPException(422, "Choose a list or name a new one")
    ids = set(db.scalars(select(Contact.id).where(Contact.id.in_(data.contact_ids))))
    added = _add(db, ml.id, ids, "manual")
    audit(db, user, "mailing_list", ml.id, "add_members", {"added": added})
    db.commit()
    return {"list_id": ml.id, "list_name": ml.name, "added": added, "already_in_list": len(ids) - added}


# ---------------- overview ----------------
@router.get("/marketing/overview")
def marketing_overview(days: int = Query(90, ge=7, le=730), db: Session = Depends(get_db),
                       _: User = Depends(get_current_user)):
    """Reach of the contact base, and how recent campaigns performed."""
    has_email = Contact.email.contains("@")
    n = lambda *conds: db.scalar(select(func.count()).select_from(Contact).where(has_email, *conds)) or 0  # noqa: E731
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    r = CampaignRecipient
    sent_q = select(func.count()).select_from(r).where(r.status == "sent", r.sent_at >= since)
    sent = db.scalar(sent_q) or 0
    opened = db.scalar(sent_q.where(r.opened_at.is_not(None))) or 0
    clicked = db.scalar(sent_q.where(r.clicked_at.is_not(None))) or 0
    unsub = db.scalar(sent_q.where(r.unsubscribed_at.is_not(None))) or 0
    failed = db.scalar(select(func.count()).select_from(r).where(r.status == "failed", r.campaign_id.in_(
        select(Campaign.id).where(Campaign.started_at >= since)))) or 0
    recent = db.scalars(select(Campaign).where(Campaign.status != "draft")
                        .order_by(func.coalesce(Campaign.started_at, Campaign.scheduled_at, Campaign.created_at).desc())
                        .limit(8)).all()
    by_status = dict(db.execute(select(Campaign.status, func.count()).group_by(Campaign.status)).all())
    new_subs = db.scalar(select(func.count()).select_from(ListMember).where(
        ListMember.added_at >= since, ListMember.status == "subscribed")) or 0
    return {
        "days": days,
        "contacts": {"with_email": n(), "reachable": n(Contact.unsubscribed.is_(False)),
                     "with_consent": n(Contact.unsubscribed.is_(False), Contact.consent_marketing.is_(True)),
                     "unsubscribed": n(Contact.unsubscribed.is_(True))},
        "lists": db.scalar(select(func.count()).select_from(MailingList)) or 0,
        "audiences": db.scalar(select(func.count()).select_from(Audience)) or 0,
        "new_subscriptions": new_subs,
        "campaigns": by_status,
        "email": {"sent": sent, "opened": opened, "clicked": clicked, "unsubscribed": unsub, "failed": failed,
                  "open_rate": round(100 * opened / sent, 1) if sent else 0.0,
                  "click_rate": round(100 * clicked / sent, 1) if sent else 0.0,
                  "unsubscribe_rate": round(100 * unsub / sent, 1) if sent else 0.0},
        "recent": [{"id": c.id, "name": c.name, "kind": c.kind, "status": c.status,
                    "date": c.started_at or c.scheduled_at, "stats": cmp.stats(db, c)} for c in recent],
    }

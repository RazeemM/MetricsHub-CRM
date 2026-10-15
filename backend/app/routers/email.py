"""Email marketing: templates, mailing lists, campaigns/newsletters, and the mail server status."""
import csv
import datetime as dt
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from .. import campaigns as cmp
from .. import mail
from ..config import get_settings
from ..crud import apply_changes, audit, get_or_404, paginate
from ..db import get_db
from ..email_starters import starters
from ..models import (
    Account,
    Brand,
    Campaign,
    CampaignRecipient,
    Contact,
    EmailTemplate,
    ListMember,
    MailingList,
    User,
)
from ..security import get_current_user, require_admin, require_writer

router = APIRouter(prefix="/api", tags=["email"])


# ---------------- mail server ----------------
@router.get("/mail/settings")
def mail_settings(_: User = Depends(get_current_user)):
    s = get_settings()
    return {
        "transactional": mail.status("transactional"), "bulk": mail.status("bulk"),
        "smtp": {"host": s.smtp_host or None, "port": s.smtp_port, "security": s.smtp_security,
                 "username": s.smtp_username or None},
        "from": s.mail_from or None, "from_name": s.mail_from_name or None,
        "rate_per_minute": s.bulk_rate_per_minute, "postal_address": s.marketing_postal_address or None,
        "merge_fields": cmp.MERGE_FIELDS,
    }


class TestMailIn(BaseModel):
    to: EmailStr
    purpose: str = Field(default="transactional", pattern="^(transactional|bulk)$")


@router.post("/mail/test")
def mail_test(data: TestMailIn, user: User = Depends(require_admin)):
    """Send a test message through the configured server, to check the settings."""
    try:
        mail.send(mail.Message(sender=mail.sender_for(user.email, data.purpose), to=[data.to],
                               subject="CRM test email", html="<p>The CRM can send email through this server.</p>"),
                  data.purpose)
    except mail.MailError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"sent": True, "backend": mail.backend_for(data.purpose)}


# ---------------- templates ----------------
class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    brand_id: int | None = None
    subject: str = Field(min_length=1, max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    body_html: str = Field(min_length=1, max_length=500_000)


class TemplateOut(TemplateIn):
    model_config = {"from_attributes": True}
    id: int
    updated_at: dt.datetime


class PreviewIn(BaseModel):
    subject: str = ""
    preheader: str | None = None
    body_html: str = ""
    contact_id: int | None = None


@router.get("/email-templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(EmailTemplate).order_by(EmailTemplate.name)).all()


@router.get("/email-templates/starters")
def template_starters(brand_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    brand = db.get(Brand, brand_id) if brand_id else None
    sentry = brand is not None and brand.code == "SENTRY"
    return starters(brand.name if brand else "MetricsHub", "#F28C38" if sentry else "#7C5CFF")


@router.post("/email-templates", response_model=TemplateOut, status_code=201)
def create_template(data: TemplateIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    t = EmailTemplate(**data.model_dump(), updated_by_id=user.id)
    db.add(t)
    db.flush()
    audit(db, user, "email_template", t.id, "create", {"name": t.name})
    db.commit()
    db.refresh(t)
    return t


@router.get("/email-templates/{tid}", response_model=TemplateOut)
def get_template(tid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return get_or_404(db, EmailTemplate, tid)


@router.put("/email-templates/{tid}", response_model=TemplateOut)
def update_template(tid: int, data: TemplateIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    t = get_or_404(db, EmailTemplate, tid)
    changes = apply_changes(t, data)
    changes.pop("body_html", None) and changes.setdefault("body_html", "changed")
    t.updated_by_id = user.id
    audit(db, user, "email_template", t.id, "update", changes)
    db.commit()
    db.refresh(t)
    return t


@router.delete("/email-templates/{tid}", status_code=204)
def delete_template(tid: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    t = get_or_404(db, EmailTemplate, tid)
    audit(db, user, "email_template", t.id, "delete", {"name": t.name})
    db.delete(t)
    db.commit()


@router.post("/email-templates/preview")
def preview(data: PreviewIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Render subject and HTML with a sample (or a chosen) contact; links are not tracked in previews."""
    values = dict(cmp.SAMPLE)
    if data.contact_id and (ct := db.get(Contact, data.contact_id)):
        values = cmp.contact_values(ct)
    c = Campaign(subject=data.subject, preheader=data.preheader, body_html=data.body_html,
                 track_opens=False, track_clicks=False)
    subject, body = cmp.personalise(c, values, "preview", track=False)
    return {"subject": subject, "html": body}


# ---------------- lists ----------------
class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: str = Field(default="list", pattern="^(list|newsletter)$")
    description: str | None = None
    brand_id: int | None = None


class ListOut(ListIn):
    model_config = {"from_attributes": True}
    id: int
    subscribed: int = 0
    unsubscribed: int = 0
    pending: int = 0  # signed up on a web form, double opt-in not confirmed yet
    created_at: dt.datetime


class MemberFilter(BaseModel):
    lifecycle: list[str] | None = None
    role: list[str] | None = None
    account_type: list[str] | None = None
    country: list[str] | None = None
    brand_id: int | None = None
    consent_only: bool = False


class AddMembersIn(BaseModel):
    contact_ids: list[int] | None = None
    filter: MemberFilter | None = None


def _list_out(db: Session, ml: MailingList) -> ListOut:
    counts = dict(db.execute(select(ListMember.status, func.count()).where(ListMember.list_id == ml.id)
                             .group_by(ListMember.status)).all())
    return ListOut(id=ml.id, name=ml.name, kind=ml.kind, description=ml.description, brand_id=ml.brand_id,
                   created_at=ml.created_at, subscribed=counts.get("subscribed", 0),
                   unsubscribed=counts.get("unsubscribed", 0), pending=counts.get("pending", 0))


@router.get("/lists", response_model=list[ListOut])
def list_lists(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_list_out(db, ml) for ml in db.scalars(select(MailingList).order_by(MailingList.name))]


@router.post("/lists", response_model=ListOut, status_code=201)
def create_list(data: ListIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    if db.scalar(select(MailingList).where(func.lower(MailingList.name) == data.name.lower())):
        raise HTTPException(409, "A list with this name already exists")
    ml = MailingList(**data.model_dump())
    db.add(ml)
    db.flush()
    audit(db, user, "mailing_list", ml.id, "create", {"name": ml.name})
    db.commit()
    return _list_out(db, ml)


@router.put("/lists/{lid}", response_model=ListOut)
def update_list(lid: int, data: ListIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    ml = get_or_404(db, MailingList, lid)
    audit(db, user, "mailing_list", ml.id, "update", apply_changes(ml, data))
    db.commit()
    return _list_out(db, ml)


@router.delete("/lists/{lid}", status_code=204)
def delete_list(lid: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    ml = get_or_404(db, MailingList, lid)
    audit(db, user, "mailing_list", ml.id, "delete", {"name": ml.name})
    db.delete(ml)
    db.commit()


@router.get("/lists/{lid}/members")
def list_members(lid: int, q: str | None = None, status: str | None = None, page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                 _: User = Depends(get_current_user)):
    get_or_404(db, MailingList, lid)
    stmt = (select(ListMember).join(Contact, ListMember.contact_id == Contact.id)
            .options(selectinload(ListMember.contact).selectinload(Contact.account))
            .where(ListMember.list_id == lid))
    if status:
        stmt = stmt.where(ListMember.status == status)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Contact.email.ilike(term), Contact.first_name.ilike(term),
                              Contact.last_name.ilike(term)))
    items, total = paginate(db, stmt.order_by(ListMember.added_at.desc()), page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": [{
        "id": m.id, "contact_id": m.contact_id, "name": m.contact.full_name, "email": m.contact.email,
        "company": m.contact.account.name if m.contact.account else None, "status": m.status, "source": m.source,
        "added_at": m.added_at, "consent": m.contact.consent_marketing,
        "globally_unsubscribed": m.contact.unsubscribed} for m in items]}


def _add(db: Session, lid: int, contact_ids: set[int], source: str) -> int:
    existing = set(db.scalars(select(ListMember.contact_id).where(ListMember.list_id == lid)))
    new = [cid for cid in contact_ids if cid not in existing]
    db.add_all(ListMember(list_id=lid, contact_id=cid, status="subscribed", source=source) for cid in new)
    return len(new)


@router.post("/lists/{lid}/members")
def add_members(lid: int, data: AddMembersIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Add chosen contacts, or every contact matching a filter (e.g. all leads in one country)."""
    get_or_404(db, MailingList, lid)
    ids: set[int] = set(data.contact_ids or [])
    if data.filter:
        f = data.filter
        stmt = select(Contact.id).where(Contact.email.is_not(None))
        if f.lifecycle:
            stmt = stmt.where(Contact.lifecycle.in_(f.lifecycle))
        if f.role:
            stmt = stmt.where(Contact.role.in_(f.role))
        if f.country:
            stmt = stmt.where(func.lower(Contact.country).in_([c.lower() for c in f.country]))
        if f.account_type:
            stmt = stmt.where(Contact.account.has(Account.account_type.in_(f.account_type)))
        if f.brand_id:
            stmt = stmt.where(Contact.brand_id == f.brand_id)
        if f.consent_only:
            stmt = stmt.where(Contact.consent_marketing.is_(True))
        ids |= set(db.scalars(stmt))
    added = _add(db, lid, ids, "filter" if data.filter else "manual")
    audit(db, user, "mailing_list", lid, "add_members", {"added": added})
    db.commit()
    return {"added": added, "already_in_list": len(ids) - added}


@router.post("/lists/{lid}/import")
def import_members(lid: int, file: UploadFile = File(...), consent: bool = Form(False),
                   db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """CSV with an email column (first_name, last_name, company optional). Unknown emails become new contacts.
    consent=true records that these people agreed to receive marketing email."""
    get_or_404(db, MailingList, lid)
    raw = file.file.read(10_000_001)
    if len(raw) > 10_000_000:
        raise HTTPException(413, "File too large (max 10 MB)")
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=",;\t").delimiter
    except csv.Error:
        dialect = ","
    rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=dialect))
    norm = lambda k: (k or "").strip().lower().replace(" ", "_")  # noqa: E731
    created, ids, bad = 0, set(), 0
    for row in rows:
        r = {norm(k): (v or "").strip() for k, v in row.items()}
        email = (r.get("email") or r.get("e-mail") or r.get("email_address") or "").lower()
        if "@" not in email or len(email) > 255:
            bad += 1
            continue
        ct = db.scalar(select(Contact).where(func.lower(Contact.email) == email))
        if not ct:
            ct = Contact(email=email, first_name=r.get("first_name") or None, last_name=r.get("last_name") or None,
                         source="import", lifecycle="lead", extra={})
            if r.get("company"):
                ct.extra = {"company": r["company"]}
            db.add(ct)
            db.flush()
            created += 1
        if consent and not ct.consent_marketing:
            ct.consent_marketing, ct.consent_at = True, dt.datetime.now(dt.UTC)
        ids.add(ct.id)
    added = _add(db, lid, ids, "import")
    audit(db, user, "mailing_list", lid, "import", {"file": file.filename, "added": added, "new_contacts": created})
    db.commit()
    return {"rows": len(rows), "added": added, "new_contacts": created, "invalid_rows": bad}


class MemberStatus(BaseModel):
    status: str = Field(pattern="^(subscribed|unsubscribed)$")


@router.patch("/lists/{lid}/members/{mid}")
def set_member_status(lid: int, mid: int, data: MemberStatus, db: Session = Depends(get_db),
                      user: User = Depends(require_writer)):
    m = get_or_404(db, ListMember, mid)
    if m.list_id != lid:
        raise HTTPException(404, "Not a member of this list")
    m.status = data.status
    m.unsubscribed_at = dt.datetime.now(dt.UTC) if data.status == "unsubscribed" else None
    audit(db, user, "mailing_list", lid, "member_status", {"contact_id": m.contact_id, "status": data.status})
    db.commit()
    return {"ok": True}


@router.delete("/lists/{lid}/members/{mid}", status_code=204)
def remove_member(lid: int, mid: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    db.execute(delete(ListMember).where(ListMember.id == mid, ListMember.list_id == lid))
    audit(db, user, "mailing_list", lid, "remove_member", {"member_id": mid})
    db.commit()


# ---------------- campaigns ----------------
class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="campaign", pattern="^(campaign|newsletter)$")
    brand_id: int | None = None
    template_id: int | None = None
    subject: str = Field(default="", max_length=255)
    preheader: str | None = Field(default=None, max_length=255)
    body_html: str = Field(default="", max_length=500_000)
    from_name: str | None = Field(default=None, max_length=120)
    reply_to: EmailStr | None = None
    list_ids: list[int] = Field(default_factory=list)
    require_consent: bool = False
    track_opens: bool = True
    track_clicks: bool = True


class CampaignOut(CampaignIn):
    model_config = {"from_attributes": True}
    id: int
    status: str
    scheduled_at: dt.datetime | None
    started_at: dt.datetime | None
    finished_at: dt.datetime | None
    last_error: str | None
    created_at: dt.datetime
    stats: dict | None = None


def _out(db: Session, c: Campaign) -> CampaignOut:
    o = CampaignOut.model_validate(c)
    o.stats = cmp.stats(db, c) if c.status != "draft" else None
    return o


def _editable(c: Campaign):
    if c.status not in ("draft", "scheduled"):
        raise HTTPException(409, "This campaign has started: its content can no longer change")


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_out(db, c) for c in db.scalars(select(Campaign).order_by(Campaign.created_at.desc()))]


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(data: CampaignIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    values = data.model_dump()
    if data.template_id and not data.body_html:  # start from the template's content
        t = get_or_404(db, EmailTemplate, data.template_id)
        values.update(subject=data.subject or t.subject, preheader=data.preheader or t.preheader,
                      body_html=t.body_html, brand_id=data.brand_id or t.brand_id)
    if data.kind == "newsletter":
        values["require_consent"] = True
    c = Campaign(**values, created_by_id=user.id, status="draft")
    db.add(c)
    db.flush()
    audit(db, user, "campaign", c.id, "create", {"name": c.name})
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.get("/campaigns/{cid}", response_model=CampaignOut)
def get_campaign(cid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _out(db, get_or_404(db, Campaign, cid))


@router.put("/campaigns/{cid}", response_model=CampaignOut)
def update_campaign(cid: int, data: CampaignIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    c = get_or_404(db, Campaign, cid)
    _editable(c)
    changes = apply_changes(c, data)
    changes.pop("body_html", None) and changes.setdefault("body_html", "changed")
    audit(db, user, "campaign", c.id, "update", changes)
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.delete("/campaigns/{cid}", status_code=204)
def delete_campaign(cid: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    c = get_or_404(db, Campaign, cid)
    if c.status in ("sending", "sent", "paused"):
        raise HTTPException(409, "A campaign that has sent email is kept for its report; cancel it instead")
    audit(db, user, "campaign", c.id, "delete", {"name": c.name})
    db.delete(c)
    db.commit()


@router.get("/campaigns/{cid}/audience")
def campaign_audience(cid: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """How many people will receive it, and how many are left out and why."""
    return cmp.audience_summary(db, get_or_404(db, Campaign, cid))


class TestSendIn(BaseModel):
    to: list[EmailStr] = Field(min_length=1, max_length=5)
    contact_id: int | None = None


@router.post("/campaigns/{cid}/test")
def test_send(cid: int, data: TestSendIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    c = get_or_404(db, Campaign, cid)
    if not c.subject or not c.body_html:
        raise HTTPException(422, "Add a subject and content first")
    values = cmp.contact_values(ct) if data.contact_id and (ct := db.get(Contact, data.contact_id)) \
        else {**cmp.SAMPLE, "owner": user.full_name}
    try:
        with mail.MailSession("bulk") as session:
            for to in data.to:
                msg = cmp.build_message(c, to, values, "test", track=False)
                msg.subject = f"[TEST] {msg.subject}"
                session.send(msg)
    except mail.MailError as exc:
        raise HTTPException(502, str(exc)) from None
    return {"sent": len(data.to)}


class SendIn(BaseModel):
    scheduled_at: dt.datetime | None = None


@router.post("/campaigns/{cid}/send", response_model=CampaignOut)
def send_campaign(cid: int, data: SendIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Send now (queued, delivered in the background) or schedule for later."""
    c = get_or_404(db, Campaign, cid)
    _editable(c)
    if not c.subject or not c.body_html or not c.list_ids:
        raise HTTPException(422, "A campaign needs a subject, content and at least one list")
    if not mail.status("bulk")["enabled"]:
        raise HTTPException(503, "Bulk email is not configured on this server (CRM_BULK_MAIL_BACKEND / SMTP)")
    if not get_settings().mail_from:
        raise HTTPException(503, "Set CRM_MAIL_FROM: campaigns are sent from that address")
    if cmp.audience_summary(db, c)["recipients"] == 0:
        raise HTTPException(422, "Nobody in the chosen lists can receive this campaign")
    if data.scheduled_at and data.scheduled_at > dt.datetime.now(dt.UTC):
        c.status, c.scheduled_at = "scheduled", data.scheduled_at
    else:
        cmp.prepare(db, c)
    audit(db, user, "campaign", c.id, "send", {"scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None})
    db.commit()
    db.refresh(c)
    return _out(db, c)


class ActionIn(BaseModel):
    action: str = Field(pattern="^(pause|resume|cancel|unschedule)$")


@router.post("/campaigns/{cid}/action", response_model=CampaignOut)
def campaign_action(cid: int, data: ActionIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    c = get_or_404(db, Campaign, cid)
    allowed = {"pause": ("sending",), "resume": ("paused",), "cancel": ("scheduled", "sending", "paused"),
               "unschedule": ("scheduled",)}
    if c.status not in allowed[data.action]:
        raise HTTPException(409, f"Cannot {data.action} a {c.status} campaign")
    if data.action == "pause":
        c.status = "paused"
    elif data.action == "resume":
        c.status, c.last_error = "sending", None
    elif data.action == "unschedule":
        c.status, c.scheduled_at = "draft", None
    else:
        c.status, c.finished_at = "cancelled", dt.datetime.now(dt.UTC)
        db.query(CampaignRecipient).filter(CampaignRecipient.campaign_id == c.id,
                                           CampaignRecipient.status == "queued").update(
            {"status": "skipped", "reason": "campaign cancelled"})
    audit(db, user, "campaign", c.id, data.action)
    db.commit()
    db.refresh(c)
    return _out(db, c)


@router.get("/campaigns/{cid}/recipients")
def campaign_recipients(cid: int, status: str | None = None, q: str | None = None, page: int = Query(1, ge=1),
                        page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                        _: User = Depends(get_current_user)):
    get_or_404(db, Campaign, cid)
    stmt = select(CampaignRecipient).where(CampaignRecipient.campaign_id == cid)
    if status == "opened":
        stmt = stmt.where(CampaignRecipient.opened_at.is_not(None))
    elif status == "clicked":
        stmt = stmt.where(CampaignRecipient.clicked_at.is_not(None))
    elif status == "unsubscribed":
        stmt = stmt.where(CampaignRecipient.unsubscribed_at.is_not(None))
    elif status:
        stmt = stmt.where(CampaignRecipient.status == status)
    if q:
        stmt = stmt.where(CampaignRecipient.email.ilike(f"%{q.strip()}%"))
    items, total = paginate(db, stmt.order_by(CampaignRecipient.id), page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": [{
        "id": r.id, "contact_id": r.contact_id, "email": r.email, "status": r.status, "reason": r.reason,
        "sent_at": r.sent_at, "opened_at": r.opened_at, "open_count": r.open_count, "clicked_at": r.clicked_at,
        "click_count": r.click_count, "unsubscribed_at": r.unsubscribed_at} for r in items]}


@router.get("/contacts/{contact_id}/campaigns")
def contact_campaigns(contact_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Campaigns a contact received (shown on the contact page)."""
    rows = db.execute(select(CampaignRecipient, Campaign.name).join(Campaign, Campaign.id == CampaignRecipient.campaign_id)
                      .where(CampaignRecipient.contact_id == contact_id)
                      .order_by(CampaignRecipient.id.desc()).limit(100)).all()
    lists = db.execute(select(MailingList.id, MailingList.name, ListMember.status)
                       .join(ListMember, ListMember.list_id == MailingList.id)
                       .where(ListMember.contact_id == contact_id)).all()
    return {"campaigns": [{"campaign_id": r.campaign_id, "name": n, "status": r.status, "sent_at": r.sent_at,
                           "opened_at": r.opened_at, "clicked_at": r.clicked_at,
                           "unsubscribed_at": r.unsubscribed_at} for r, n in rows],
            "lists": [{"id": i, "name": n, "status": s} for i, n, s in lists]}

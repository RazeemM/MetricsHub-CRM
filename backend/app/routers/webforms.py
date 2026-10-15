"""Administration of website forms (the public endpoint is in routers/public.py)."""
import datetime as dt
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import webforms as wf
from ..config import get_settings
from ..crud import apply_changes, audit, get_or_404, paginate
from ..db import get_db
from ..enums import LeadSource
from ..models import Brand, FormSubmission, MailingList, User, WebForm
from ..security import require_admin

router = APIRouter(prefix="/api/web-forms", tags=["web forms"])


class WebFormIn(BaseModel):
    key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    name: str = Field(min_length=1, max_length=160)
    brand_id: int | None = None
    lead_source: LeadSource = LeadSource.website_contact
    field_map: dict[str, str] = Field(default_factory=dict)
    owner_id: int | None = None
    list_id: int | None = None
    auth_mode: str = Field(default="hmac", pattern="^(hmac|token)$")
    allowed_origins: list[str] = Field(default_factory=list)
    honeypot_field: str | None = Field(default="website", max_length=64)
    redirect_url: str | None = Field(default=None, max_length=500)
    confirm_redirect_url: str | None = Field(default=None, max_length=500)
    confirm_subject: str | None = Field(default=None, max_length=255)
    confirm_body_html: str | None = Field(default=None, max_length=200_000)
    notify_owner: bool = True
    rate_limit_per_hour: int = Field(default=20, ge=0, le=10_000)
    active: bool = True

    @field_validator("field_map")
    @classmethod
    def _targets(cls, v: dict[str, str]) -> dict[str, str]:
        out = {}
        for k, target in v.items():
            if not k.strip():
                continue
            if target not in wf.CONTACT_FIELDS:
                raise ValueError(f"'{target}' is not a contact field")
            out[k.strip()[:100]] = target
        return out

    @field_validator("allowed_origins")
    @classmethod
    def _origins(cls, v: list[str]) -> list[str]:
        out = []
        for o in v:
            o = o.strip().rstrip("/")
            if not o:
                continue
            if not o.startswith(("http://", "https://")) or "/" in o.split("://", 1)[1]:
                raise ValueError(f"'{o}' is not an origin like https://www.example.com")
            out.append(o.lower())
        return out

    @field_validator("redirect_url", "confirm_redirect_url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        v = (v or "").strip() or None
        if v and not v.startswith(("http://", "https://")):
            raise ValueError("must start with https://")
        return v

    @field_validator("honeypot_field", "confirm_subject", "confirm_body_html")
    @classmethod
    def _blank(cls, v: str | None) -> str | None:
        return (v or "").strip() or None


class WebFormOut(WebFormIn):
    model_config = {"from_attributes": True}
    id: int
    secret: str
    endpoint: str = ""
    list_kind: str | None = None
    submissions_30d: int = 0
    last_submission_at: dt.datetime | None = None
    created_at: dt.datetime


def _out(db: Session, f: WebForm) -> WebFormOut:
    o = WebFormOut.model_validate(f)
    o.endpoint = f"{get_settings().app_url}/api/public/forms/{f.key}"
    o.list_kind = f.mailing_list.kind if f.mailing_list else None
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=30)
    o.submissions_30d = db.scalar(select(func.count()).select_from(FormSubmission).where(
        FormSubmission.form_id == f.id, FormSubmission.created_at >= since)) or 0
    o.last_submission_at = db.scalar(select(func.max(FormSubmission.created_at)).where(FormSubmission.form_id == f.id))
    return o


def _check(db: Session, data: WebFormIn, form_id: int | None = None) -> None:
    other = db.scalar(select(WebForm).where(WebForm.key == data.key))
    if other and other.id != form_id:
        raise HTTPException(409, "Another form already uses this key")
    if data.brand_id and not db.get(Brand, data.brand_id):
        raise HTTPException(422, "Brand not found")
    if data.list_id and not db.get(MailingList, data.list_id):
        raise HTTPException(422, "Mailing list not found")
    if data.owner_id:
        owner = db.get(User, data.owner_id)
        if not owner or not owner.is_active:
            raise HTTPException(422, "Owner not found")


@router.get("/meta")
def meta(_: User = Depends(require_admin)):
    return {"contact_fields": wf.CONTACT_FIELDS, "aliases": wf.ALIASES,
            "endpoint_base": f"{get_settings().app_url}/api/public/forms/"}


@router.get("", response_model=list[WebFormOut])
def list_forms(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_out(db, f) for f in db.scalars(select(WebForm).order_by(WebForm.name))]


@router.post("", response_model=WebFormOut, status_code=201)
def create_form(data: WebFormIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    _check(db, data)
    f = WebForm(**data.model_dump(), secret=secrets.token_urlsafe(32))
    db.add(f)
    db.flush()
    audit(db, user, "web_form", f.id, "create", {"key": f.key, "name": f.name})
    db.commit()
    db.refresh(f)
    return _out(db, f)


@router.get("/{fid}", response_model=WebFormOut)
def get_form(fid: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _out(db, get_or_404(db, WebForm, fid))


@router.put("/{fid}", response_model=WebFormOut)
def update_form(fid: int, data: WebFormIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    f = get_or_404(db, WebForm, fid)
    _check(db, data, fid)
    changes = apply_changes(f, data)
    changes.pop("confirm_body_html", None) and changes.setdefault("confirm_body_html", "changed")
    audit(db, user, "web_form", f.id, "update", changes)
    db.commit()
    db.refresh(f)
    return _out(db, f)


@router.delete("/{fid}", status_code=204)
def delete_form(fid: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    f = get_or_404(db, WebForm, fid)
    audit(db, user, "web_form", f.id, "delete", {"key": f.key})
    db.delete(f)
    db.commit()


@router.post("/{fid}/rotate-secret", response_model=WebFormOut)
def rotate_secret(fid: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """A new secret: the website must be updated, the old one stops working at once."""
    f = get_or_404(db, WebForm, fid)
    f.secret = secrets.token_urlsafe(32)
    audit(db, user, "web_form", f.id, "rotate_secret")
    db.commit()
    db.refresh(f)
    return _out(db, f)


class TestIn(BaseModel):
    fields: dict[str, str | bool | None] = Field(min_length=1)


@router.post("/{fid}/test")
def test_form(fid: int, data: TestIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Process a submission as if the website had posted it (no secret or rate limit), to check the mapping."""
    f = get_or_404(db, WebForm, fid)
    sub = wf.submit(db, f, data.fields, user_agent=f"CRM test by {user.email}")
    db.commit()
    if sub.status == "pending":
        wf.send_confirmation(sub.id)
        db.refresh(sub)
    return _submission(sub)


def _submission(s: FormSubmission) -> dict:
    return {"id": s.id, "created_at": s.created_at, "status": s.status, "email": s.email, "contact_id": s.contact_id,
            "contact_created": s.contact_created, "data": s.data, "ip": s.ip, "note": s.note}


@router.get("/{fid}/submissions")
def submissions(fid: int, status: str | None = None, page: int = Query(1, ge=1),
                page_size: int = Query(50, ge=1, le=200), db: Session = Depends(get_db),
                _: User = Depends(require_admin)):
    get_or_404(db, WebForm, fid)
    stmt = select(FormSubmission).where(FormSubmission.form_id == fid)
    if status:
        stmt = stmt.where(FormSubmission.status == status)
    items, total = paginate(db, stmt.order_by(FormSubmission.id.desc()), page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": [_submission(s) for s in items]}

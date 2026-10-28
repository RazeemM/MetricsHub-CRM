import datetime as dt
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import mail
from ..crud import apply_changes, audit, get_or_404
from ..db import get_db
from ..models import Activity, Brand, Opportunity, Quote, User
from ..quotes import (
    DEFAULT_EMAIL_BODY,
    DEFAULT_EMAIL_SUBJECT,
    PLACEHOLDERS,
    build_quote,
    default_template,
    fill,
    get_or_create_template,
    placeholder_values,
    quote_to_data,
    render_html,
    render_pdf,
    rich,
    sample_data,
    template_dict,
)
from ..security import get_current_user, require_admin, require_writer

router = APIRouter(prefix="/api", tags=["quotes"])

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
LOGO = re.compile(r"^data:image/(png|jpeg|webp|svg\+xml);base64,[A-Za-z0-9+/=]+$")
MAX_LOGO = 700_000  # ~500 KB image


class TemplateIn(BaseModel):
    company_name: str = Field(min_length=1, max_length=200)
    address: str | None = None
    vat_number: str | None = None
    registration: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    logo_data_uri: str | None = None
    logo_height: int = Field(default=36, ge=16, le=120)
    header_show_name: bool = True
    header_bg: str = "#141A22"
    header_text_color: str = "#FFFFFF"
    accent_color: str = "#7C5CFF"
    title: str = Field(default="Quotation", min_length=1, max_length=80)
    intro_text: str | None = None
    terms_text: str | None = None
    payment_terms: str | None = None
    validity_days: int = Field(default=30, ge=1, le=365)
    footer_text: str | None = None
    show_discount: bool = True
    show_signature: bool = True
    email_subject: str | None = Field(default=None, max_length=255)
    email_body: str | None = None

    @field_validator("header_bg", "header_text_color", "accent_color")
    @classmethod
    def color(cls, v: str) -> str:
        if not HEX.match(v):
            raise ValueError("use a #RRGGBB colour")
        return v

    @field_validator("logo_data_uri")
    @classmethod
    def logo(cls, v: str | None) -> str | None:
        if not v:
            return None
        if len(v) > MAX_LOGO or not LOGO.match(v):
            raise ValueError("logo must be a PNG, JPEG, WebP or SVG image under 500 KB")
        return v


class TemplateOut(TemplateIn):
    brand_id: int
    brand_name: str
    logo_data_uri: str | None = None

    @field_validator("logo_data_uri")
    @classmethod
    def logo(cls, v):  # no validation on output
        return v


class QuoteCreate(BaseModel):
    valid_days: int | None = Field(default=None, ge=1, le=365)
    notes: str | None = None


class QuoteStatus(BaseModel):
    status: Literal["draft", "sent", "accepted", "rejected", "expired"]


class QuoteOut(BaseModel):
    id: int
    opportunity_id: int
    number: str
    version: int
    display_number: str
    status: str
    issue_date: str
    valid_until: str
    currency: str
    amount_tcv: str
    amount_arr: str
    created_by: str | None
    created_at: str
    line_count: int


def _out(q: Quote) -> QuoteOut:
    return QuoteOut(
        id=q.id, opportunity_id=q.opportunity_id, number=q.number, version=q.version,
        display_number=q.number if q.version == 1 else f"{q.number} v{q.version}", status=q.status,
        issue_date=q.issue_date.isoformat(), valid_until=q.valid_until.isoformat(), currency=q.currency,
        amount_tcv=str(q.amount_tcv), amount_arr=str(q.amount_arr),
        created_by=q.created_by.full_name if q.created_by else None, created_at=q.created_at.isoformat(),
        line_count=len(q.lines))


# ---------------- templates ----------------
@router.get("/quote-templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    out = []
    for brand in db.scalars(select(Brand).order_by(Brand.id)):
        tpl = get_or_create_template(db, brand.id)
        out.append(TemplateOut(brand_id=brand.id, brand_name=brand.name, **template_dict(tpl)))
    db.commit()
    return out


@router.put("/quote-templates/{brand_id}", response_model=TemplateOut)
def save_template(brand_id: int, data: TemplateIn, db: Session = Depends(get_db),
                  user: User = Depends(require_admin)):
    brand = get_or_404(db, Brand, brand_id)
    tpl = get_or_create_template(db, brand_id)
    changes = apply_changes(tpl, data)
    if changes.pop("logo_data_uri", None):  # don't store image data in the audit log
        changes["logo"] = "replaced"
    audit(db, user, "quote_template", tpl.id, "update", changes)
    db.commit()
    return TemplateOut(brand_id=brand.id, brand_name=brand.name, **template_dict(tpl))


@router.post("/quote-templates/{brand_id}/reset", response_model=TemplateOut)
def reset_template(brand_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    brand = get_or_404(db, Brand, brand_id)
    tpl = get_or_create_template(db, brand_id)
    for k, v in default_template(brand).items():
        setattr(tpl, k, v)
    audit(db, user, "quote_template", tpl.id, "reset")
    db.commit()
    return TemplateOut(brand_id=brand.id, brand_name=brand.name, **template_dict(tpl))


@router.post("/quote-templates/preview", response_class=HTMLResponse)
def preview_template(data: TemplateIn, _: User = Depends(get_current_user)):
    """Render unsaved template settings with sample data (used for the live preview)."""
    return HTMLResponse(render_html(sample_data(), data.model_dump()))


@router.post("/quote-templates/preview.pdf")
def preview_template_pdf(data: TemplateIn, _: User = Depends(get_current_user)):
    pdf = render_pdf(render_html(sample_data(), data.model_dump()))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="quote-preview.pdf"'})


@router.get("/quote-templates/placeholders")
def placeholders(_: User = Depends(get_current_user)):
    return PLACEHOLDERS


# ---------------- quotes ----------------
def _load_opp(db: Session, opp_id: int) -> Opportunity:
    opp = db.scalar(select(Opportunity).options(selectinload(Opportunity.line_items), selectinload(Opportunity.account),
                                                selectinload(Opportunity.primary_contact))
                    .where(Opportunity.id == opp_id))
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    return opp


@router.get("/opportunities/{opp_id}/quotes", response_model=list[QuoteOut])
def list_quotes(opp_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    qs = db.scalars(select(Quote).options(selectinload(Quote.created_by))
                    .where(Quote.opportunity_id == opp_id).order_by(Quote.version.desc()))
    return [_out(q) for q in qs]


@router.post("/opportunities/{opp_id}/quotes", response_model=QuoteOut, status_code=201)
def create_quote(opp_id: int, data: QuoteCreate, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    opp = _load_opp(db, opp_id)
    if not opp.line_items:
        raise HTTPException(422, "Add at least one product to the opportunity before generating a quote")
    q = build_quote(db, opp, user.id, data.valid_days, data.notes)
    db.add(q)
    db.flush()
    audit(db, user, "quote", q.id, "create", {"number": q.number, "version": q.version})
    db.commit()
    db.refresh(q)
    return _out(q)


@router.patch("/quotes/{quote_id}", response_model=QuoteOut)
def set_status(quote_id: int, data: QuoteStatus, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    q = get_or_404(db, Quote, quote_id)
    audit(db, user, "quote", q.id, "status", {"status": [q.status, data.status]})
    q.status = data.status
    db.commit()
    db.refresh(q)
    return _out(q)


@router.delete("/quotes/{quote_id}", status_code=204)
def delete_quote(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    q = get_or_404(db, Quote, quote_id)
    if q.status != "draft":
        raise HTTPException(409, "Only draft quotes can be deleted")
    audit(db, user, "quote", q.id, "delete", {"number": q.number, "version": q.version})
    db.delete(q)
    db.commit()


def _render(db: Session, q: Quote) -> str:
    opp = db.get(Opportunity, q.opportunity_id)
    owner = opp.owner.full_name if opp and opp.owner else None
    return render_html(quote_to_data(q, owner), q.template)


def _pdf_name(q: Quote) -> str:
    return f"{q.number}{'' if q.version == 1 else f'-v{q.version}'}.pdf"


@router.get("/quotes/{quote_id}/pdf")
def quote_pdf(quote_id: int, download: bool = False, db: Session = Depends(get_db),
              _: User = Depends(get_current_user)):
    q = get_or_404(db, Quote, quote_id)
    pdf = render_pdf(_render(db, q))
    disp = "attachment" if download else "inline"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'{disp}; filename="{_pdf_name(q)}"'})


# ---------------- email ----------------
class EmailDraft(BaseModel):
    enabled: bool
    sender: str
    to: list[str]
    cc: list[str]
    subject: str
    body: str
    attachment: str


class EmailIn(BaseModel):
    to: list[EmailStr] = Field(min_length=1, max_length=20)
    cc: list[EmailStr] = Field(default_factory=list, max_length=20)
    bcc: list[EmailStr] = Field(default_factory=list, max_length=20)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=20_000)


@router.get("/mail/status")
def mail_status(_: User = Depends(get_current_user)):
    return mail.status()


def _email_values(db: Session, q: Quote, user: User) -> tuple[dict, dict]:
    opp = db.get(Opportunity, q.opportunity_id)
    owner = opp.owner.full_name if opp and opp.owner else user.full_name
    tpl = template_dict(get_or_create_template(db, q.brand_id))  # current wording, not the quote's snapshot
    return placeholder_values(quote_to_data(q, owner), q.template), tpl


@router.get("/quotes/{quote_id}/email", response_model=EmailDraft)
def email_draft(quote_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Pre-filled message for the 'Email quote' dialog."""
    q = get_or_404(db, Quote, quote_id)
    values, tpl = _email_values(db, q, user)
    contact_email = (q.customer or {}).get("contact_email")
    db.commit()  # get_or_create_template may have created the brand template
    return EmailDraft(
        enabled=mail.status()["enabled"], sender=mail.sender_for(user.email),
        to=[contact_email] if contact_email else [], cc=[],
        subject=fill(tpl.get("email_subject") or DEFAULT_EMAIL_SUBJECT, values),
        body=fill(tpl.get("email_body") or DEFAULT_EMAIL_BODY, values), attachment=_pdf_name(q))


@router.post("/quotes/{quote_id}/email", response_model=QuoteOut)
def email_quote(quote_id: int, data: EmailIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Send the quote PDF from the user's Microsoft 365 mailbox, mark it sent and log the email on the deal."""
    q = get_or_404(db, Quote, quote_id)
    if q.status in ("rejected", "expired"):
        raise HTTPException(409, f"This quote is {q.status}: generate a new version instead")
    if not mail.status()["enabled"]:
        raise HTTPException(503, "Email sending is not configured on this server")
    msg = mail.Message(
        sender=mail.sender_for(user.email), to=list(data.to), cc=list(data.cc), bcc=list(data.bcc),
        subject=data.subject, html=f'<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px">'
                                   f'{rich(data.body)}</div>',
        reply_to=user.email if mail.status()["fixed_sender"] else None,
        attachments=[mail.Attachment(_pdf_name(q), render_pdf(_render(db, q)))])
    try:
        mail.send(msg)
    except mail.MailError as exc:
        raise mail.http_error(exc) from None

    opp = db.get(Opportunity, q.opportunity_id)
    contact_id = opp.primary_contact_id if opp else None
    recipients = ", ".join(data.to + data.cc)
    db.add(Activity(
        type="email", subject=data.subject[:255], opportunity_id=q.opportunity_id, contact_id=contact_id,
        body=f"Quote {_pdf_name(q)} sent from {msg.sender} to {recipients}\n\n{data.body}",
        owner_id=user.id, created_by_id=user.id, completed_at=dt.datetime.now(dt.UTC)))
    changes = {"to": data.to, "cc": data.cc, "bcc": data.bcc, "subject": data.subject}
    if q.status == "draft":
        changes["status"] = ["draft", "sent"]
        q.status = "sent"
    audit(db, user, "quote", q.id, "email", changes)
    db.commit()
    db.refresh(q)
    return _out(q)


@router.get("/quotes/{quote_id}/html", response_class=HTMLResponse)
def quote_html(quote_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return HTMLResponse(_render(db, get_or_404(db, Quote, quote_id)))

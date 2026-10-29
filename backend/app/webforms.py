"""Website forms: submissions posted by the websites create or update contacts.

A form (Contact, Quote request, Trial, Download, Partner, Newsletter...) is defined in the CRM with a key, a secret
and a mapping of its fields to contact fields. Each submission:

  1. is checked: secret (HMAC signature or token), allowed origin, rate limit per IP, honeypot and link spam
  2. creates or updates the contact by email (empty fields are filled, existing values are kept)
  3. attaches the contact to the account with the same email domain, when one exists
  4. adds the person to the form's mailing list; a newsletter list needs a double opt-in: the person gets a
     confirmation email and is only subscribed (with consent recorded) once they confirm
  5. is logged on the contact's timeline, and the owner is notified (bell)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import html
import re
import threading
import time
from collections import deque

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import campaigns as cmp
from . import mail
from .config import get_settings
from .db import SessionLocal
from .models import Account, Activity, Contact, FormSubmission, ListMember, MailingList, Notification, User, WebForm
from .services import email_domain, find_contact_by_email

CONTACT_FIELDS = {
    "email": "Email", "first_name": "First name", "last_name": "Last name",
    "full_name": "Full name (split into first and last)", "phone": "Phone", "mobile": "Mobile",
    "job_title": "Job title", "company": "Company", "country": "Country", "linkedin": "LinkedIn",
    "message": "Message (timeline only)", "consent": "Marketing consent checkbox", "ignore": "Ignore",
}
# website field names understood without a mapping
ALIASES = {
    "email": "email", "e_mail": "email", "email_address": "email", "mail": "email",
    "first_name": "first_name", "firstname": "first_name", "fname": "first_name", "given_name": "first_name",
    "last_name": "last_name", "lastname": "last_name", "lname": "last_name", "surname": "last_name",
    "family_name": "last_name", "name": "full_name", "full_name": "full_name", "fullname": "full_name",
    "phone": "phone", "telephone": "phone", "tel": "phone", "phone_number": "phone", "mobile": "mobile",
    "job_title": "job_title", "jobtitle": "job_title", "title": "job_title", "position": "job_title",
    "company": "company", "company_name": "company", "organization": "company", "organisation": "company",
    "country": "country", "linkedin": "linkedin", "message": "message", "comments": "message",
    "comment": "message", "consent": "consent", "newsletter": "consent", "opt_in": "consent",
    "optin": "consent", "marketing_consent": "consent",
}
LENGTHS = {"first_name": 120, "last_name": 120, "phone": 60, "mobile": 60, "job_title": 160, "country": 80,
           "linkedin": 255}
EMAIL = re.compile(r"^[^@\s<>\"',;]+@[^@\s<>\"',;]+\.[^@\s<>\"',;]+$")
URL = re.compile(r"https?://|www\.", re.I)
TRUE = {"1", "true", "yes", "on", "y", "checked", "oui"}
MAX_FIELDS, MAX_VALUE = 100, 5000
SIGNATURE_MAX_AGE = 300  # seconds: an HMAC-signed request older than this is refused (replays)
CONFIRM_MAX_AGE = 7 * 86400


def norm_key(k: str) -> str:
    return re.sub(r"[\s\-.]+", "_", (k or "").strip().lower())


def clean(raw: dict) -> dict[str, str]:
    """Flatten the posted fields to short strings."""
    out: dict[str, str] = {}
    for k, v in list(raw.items())[:MAX_FIELDS]:
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v if x is not None)
        elif isinstance(v, bool):
            v = "yes" if v else "no"
        out[str(k)[:100]] = str(v).strip()[:MAX_VALUE]
    return out


def mapped(form: WebForm, data: dict[str, str]) -> dict[str, str]:
    """Contact field -> value, following the form's mapping, then the usual field names."""
    field_map = {norm_key(k): v for k, v in (form.field_map or {}).items()}
    values: dict[str, str] = {}
    for k, v in data.items():
        if k.startswith("_") or not v:
            continue
        target = field_map.get(norm_key(k)) or ALIASES.get(norm_key(k))
        if not target or target == "ignore":
            continue
        values[target] = f"{values[target]}\n{v}" if target == "message" and target in values else values.get(target, v)
    return values


def is_true(v: str | None) -> bool:
    return (v or "").strip().lower() in TRUE


# ---------------------------------------------------------------- authentication and abuse checks
def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


def authenticate(form: WebForm, headers, body: bytes, data: dict[str, str]) -> str | None:
    """None when the request carries the form's secret, else the reason it is refused."""
    if form.auth_mode == "hmac":
        ts, sig = headers.get("x-crm-timestamp", ""), headers.get("x-crm-signature", "")
        if not ts or not sig:
            return "Missing X-CRM-Timestamp / X-CRM-Signature headers"
        try:
            if abs(time.time() - int(ts)) > SIGNATURE_MAX_AGE:
                return "Signature expired: check the server clock"
        except ValueError:
            return "Invalid X-CRM-Timestamp"
        sig = sig.removeprefix("sha256=")
        return None if hmac.compare_digest(sign(form.secret, ts, body), sig) else "Invalid signature"
    token = headers.get("x-crm-form-token") or data.get("_token") or ""
    return None if hmac.compare_digest(token.encode(), form.secret.encode()) else "Invalid form token"


def origin_allowed(form: WebForm, origin: str | None) -> bool:
    """Browsers always send Origin on a cross-site POST; requests from servers (no Origin) are checked by secret."""
    if not origin or not form.allowed_origins:
        return True
    return origin.rstrip("/").lower() in {o.rstrip("/").lower() for o in form.allowed_origins}


class IpLimiter:
    """Requests per IP address over a sliding window, across all forms (also counts refused requests)."""

    def __init__(self, limit: int = 30, window: int = 600):
        self.limit, self.window = limit, window
        self.hits: dict[str, deque] = {}
        self.lock = threading.Lock()

    def allow(self, ip: str | None) -> bool:
        if not ip:
            return True
        now = time.monotonic()
        with self.lock:
            if len(self.hits) > 10_000:  # forget idle addresses
                self.hits = {k: q for k, q in self.hits.items() if q and q[-1] > now - self.window}
            q = self.hits.setdefault(ip, deque())
            while q and q[0] <= now - self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


limiter = IpLimiter()


def over_form_limit(db: Session, form: WebForm, ip: str | None) -> bool:
    if not ip or not form.rate_limit_per_hour:
        return False
    since = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    n = db.scalar(select(func.count()).select_from(FormSubmission).where(
        FormSubmission.form_id == form.id, FormSubmission.ip == ip, FormSubmission.created_at >= since))
    return (n or 0) >= form.rate_limit_per_hour


def spam_reason(form: WebForm, data: dict[str, str]) -> str | None:
    if form.honeypot_field and data.get(form.honeypot_field):
        return f"honeypot field '{form.honeypot_field}' was filled"
    links = sum(len(URL.findall(v)) for k, v in data.items() if not k.startswith("_"))
    if links > 3:
        return f"{links} links in the fields"
    return None


# ---------------------------------------------------------------- processing
def _recipients(db: Session, ct: Contact) -> list[User]:
    if ct.owner and ct.owner.is_active:
        return [ct.owner]
    return list(db.scalars(select(User).where(User.role == "admin", User.is_active.is_(True))))


def _summary(form: WebForm, data: dict[str, str], page: str | None) -> str:
    lines = [f"Submitted on the website form '{form.name}'" + (f" ({page})" if page else "")]
    lines += [f"{k}: {v}" for k, v in data.items() if not k.startswith("_") and k != form.honeypot_field and v]
    return "\n".join(lines)


def upsert_contact(db: Session, email: str, values: dict[str, str], *, lead_source: str | None,
                   brand_id: int | None, owner_id: int | None) -> tuple[Contact, bool]:
    """The contact with this email, created if new. Blank fields are filled from `values` (mapped field names), never
    overwritten; the account is matched by email domain, then by company name. Returns (contact, created)."""
    ct = find_contact_by_email(db, email)
    created = ct is None
    if ct is None:
        ct = Contact(email=email, lifecycle="lead", role="customer_contact", extra={})
        db.add(ct)
    if values.get("full_name") and not (values.get("first_name") or values.get("last_name")):
        first, _, last = values["full_name"].strip().partition(" ")
        values["first_name"], values["last_name"] = first, last.strip()
    for f, n in LENGTHS.items():
        if values.get(f) and not getattr(ct, f):
            setattr(ct, f, values[f][:n])
    ct.source = ct.source or lead_source
    ct.brand_id = ct.brand_id or brand_id
    company = (values.get("company") or "")[:255]
    if ct.account_id is None:
        domain = email_domain(email)
        acc = db.scalar(select(Account).where(func.lower(Account.domain) == domain).order_by(Account.id)) \
            if domain else None
        if acc is None and company:
            acc = db.scalar(select(Account).where(func.lower(Account.name) == company.lower()).order_by(Account.id))
        if acc is not None:
            ct.account_id = acc.id
            ct.owner_id = ct.owner_id or owner_id or acc.owner_id
        elif company and not (ct.extra or {}).get("company"):
            ct.extra = {**(ct.extra or {}), "company": company}
    ct.owner_id = ct.owner_id or owner_id
    db.flush()
    return ct, created


def submit(db: Session, form: WebForm, raw: dict, ip: str | None = None, user_agent: str | None = None,
           page: str | None = None) -> FormSubmission:
    """Process one submission (already authenticated). The caller commits, then sends the opt-in email if pending."""
    data = clean(raw)
    page = (page or data.get("_page") or "")[:300] or None
    sub = FormSubmission(form_id=form.id, data={k: v for k, v in data.items() if k != "_token"}, ip=ip,
                         user_agent=(user_agent or "")[:255] or None, status="accepted")
    db.add(sub)
    if reason := spam_reason(form, data):
        sub.status, sub.note = "spam", reason
        db.flush()
        return sub
    values = mapped(form, data)
    email = (values.get("email") or "").strip().lower()
    sub.email = email[:255] or None
    if not EMAIL.match(email) or len(email) > 255:
        sub.status, sub.note = "error", "A valid email address is required" if email else "No email field"
        db.flush()
        return sub

    now = dt.datetime.now(dt.UTC)
    ct, sub.contact_created = upsert_contact(db, email, values, lead_source=form.lead_source, brand_id=form.brand_id,
                                             owner_id=form.owner_id)
    sub.contact_id = ct.id

    # mailing list; a field mapped to "consent" makes joining depend on that checkbox
    ml = form.mailing_list
    wants_list = ml is not None and ("consent" not in (form.field_map or {}).values() or is_true(values.get("consent")))
    note = None
    if ml is not None and wants_list:
        m = db.scalar(select(ListMember).where(ListMember.list_id == ml.id, ListMember.contact_id == ct.id))
        if ml.kind == "newsletter":
            if m and m.status == "subscribed" and not ct.unsubscribed:
                note = f"Already subscribed to {ml.name}"
            else:
                if m is None:
                    m = ListMember(list_id=ml.id, contact_id=ct.id, status="pending", source="web form")
                    db.add(m)
                elif m.status == "unsubscribed" or ct.unsubscribed:
                    m.status = "pending"
                sub.status = "pending"
                note = f"Confirmation email for {ml.name} to be sent"
        elif m is None:
            db.add(ListMember(list_id=ml.id, contact_id=ct.id, status="subscribed", source="web form"))
            note = f"Added to {ml.name}"
        elif m.status == "unsubscribed":
            note = f"Not added back to {ml.name}: unsubscribed from it"
    if is_true(values.get("consent")) and not (ml is not None and ml.kind == "newsletter"):
        if ct.unsubscribed:
            note = "Ticked marketing consent, but had unsubscribed from all marketing email: left unsubscribed"
        elif not ct.consent_marketing:
            ct.consent_marketing, ct.consent_at = True, now
    sub.note = note

    body = _summary(form, data, page) + (f"\n\n{note}" if note else "")
    db.add(Activity(type="note", subject=f"Web form: {form.name}"[:255], body=body, contact_id=ct.id,
                    account_id=ct.account_id, owner_id=ct.owner_id, completed_at=now))
    db.flush()
    if form.notify_owner:
        db.refresh(ct)
        title = f"{form.name}: {ct.full_name}" + (" (new contact)" if sub.contact_created else "")
        shown = {"email": "Email", "company": "Company", "job_title": "Job title", "phone": "Phone",
                 "country": "Country", "message": "Message"}
        text = "\n".join(f"{label}: {email if k == 'email' else values[k]}" for k, label in shown.items()
                         if values.get(k))
        for user in _recipients(db, ct):
            db.add(Notification(user_id=user.id, kind="web_form", title=title[:255], body=text[:2000],
                                link=f"/contacts/{ct.id}"))
    db.flush()
    return sub


# ---------------------------------------------------------------- double opt-in
def _token_sig(payload: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), f"optin|{payload}".encode(), hashlib.sha256).hexdigest()[:32]


def confirm_token(form_id: int, list_id: int, contact_id: int, ts: int | None = None) -> str:
    payload = f"{form_id}.{list_id}.{contact_id}.{ts or int(time.time())}"
    return f"{payload}.{_token_sig(payload)}"


def read_token(token: str) -> tuple[int, int, int, int] | None:
    """(form id, list id, contact id, issued at) of a valid, unexpired confirmation token."""
    payload, _, sig = token.rpartition(".")
    if not payload or not hmac.compare_digest(_token_sig(payload), sig):
        return None
    try:
        form_id, list_id, contact_id, ts = (int(p) for p in payload.split("."))
    except ValueError:
        return None
    if time.time() - ts > CONFIRM_MAX_AGE:
        return None
    return form_id, list_id, contact_id, ts


def confirm_url(token: str) -> str:
    return f"{get_settings().app_url}/api/public/confirm/{token}"


DEFAULT_CONFIRM_SUBJECT = "Please confirm your subscription to {list_name}"
DEFAULT_CONFIRM_HTML = """<html><body style="font-family:Arial,sans-serif;color:#1f2933;background:#f2f4f7;padding:24px">
<div style="max-width:520px;margin:auto;background:#fff;border-radius:8px;padding:28px">
<p>Hello {first_name|there},</p>
<p>Thanks for signing up to <b>{list_name}</b> from {brand}. Please confirm that you want to receive it:</p>
<p style="text-align:center;margin:28px 0"><a href="{confirm_url}" style="background:#1f2933;color:#fff;padding:12px 22px;
border-radius:6px;text-decoration:none;font-weight:bold">Confirm my subscription</a></p>
<p style="font-size:13px;color:#667">If you did not sign up, ignore this email: you will not be subscribed.</p>
<p style="font-size:12px;color:#888">{postal_address}</p>
</div></body></html>"""


def build_confirmation(form: WebForm, ct: Contact, ml: MailingList) -> mail.Message:
    s = get_settings()
    brand = form.brand.name if form.brand else (s.mail_from_name or "us")
    values = {**cmp.contact_values(ct), "list_name": ml.name, "brand": brand,
              "confirm_url": confirm_url(confirm_token(form.id, ml.id, ct.id)),
              "postal_address": s.marketing_postal_address}
    subject = cmp.merge(form.confirm_subject or DEFAULT_CONFIRM_SUBJECT, values, escape=False)
    body = cmp.merge(form.confirm_body_html or DEFAULT_CONFIRM_HTML, values)
    if values["confirm_url"] not in body:  # a custom template without the link would be useless
        body += f'<p><a href="{values["confirm_url"]}">Confirm my subscription</a></p>'
    return mail.Message(sender=mail.sender_for(s.mail_from, "bulk") or s.mail_from, to=[ct.email], subject=subject,
                        html=body, from_name=form.brand.name if form.brand else None,
                        headers={"X-CRM-Form": form.key})


def send_confirmation(submission_id: int) -> None:
    """Send the double opt-in email of a pending submission (run after the request, in its own session)."""
    with SessionLocal() as db:
        sub = db.get(FormSubmission, submission_id)
        form = db.get(WebForm, sub.form_id) if sub else None
        if not sub or not form or sub.status != "pending" or not form.mailing_list or not sub.contact_id:
            return
        ct = db.get(Contact, sub.contact_id)
        try:
            mail.send(build_confirmation(form, ct, form.mailing_list), "bulk")
            sub.note = f"Confirmation email for {form.mailing_list.name} sent"
        except mail.MailError as exc:
            sub.note = f"Confirmation email not sent: {exc}"[:500]
        db.commit()


def confirm(db: Session, token: str, ip: str | None = None) -> tuple[str, WebForm | None, MailingList | None]:
    """Subscribe the person of a confirmation link. Returns (outcome, form, list): confirmed, already or invalid."""
    parsed = read_token(token)
    if not parsed:
        return "invalid", None, None
    form_id, list_id, contact_id, ts = parsed
    ml, ct = db.get(MailingList, list_id), db.get(Contact, contact_id)
    form = db.get(WebForm, form_id)
    if ml is None or ct is None:
        return "invalid", form, ml
    m = db.scalar(select(ListMember).where(ListMember.list_id == ml.id, ListMember.contact_id == ct.id))
    issued = dt.datetime.fromtimestamp(ts, dt.UTC)
    if m and m.unsubscribed_at and m.unsubscribed_at > issued:  # unsubscribed after the link was sent
        return "invalid", form, ml
    if m and m.status == "subscribed" and not ct.unsubscribed:
        return "already", form, ml
    now = dt.datetime.now(dt.UTC)
    if m is None:
        m = ListMember(list_id=ml.id, contact_id=ct.id, source="web form")
        db.add(m)
    m.status, m.unsubscribed_at = "subscribed", None
    ct.consent_marketing, ct.consent_at, ct.unsubscribed = True, now, False
    db.add(Activity(type="note", subject=f"Confirmed newsletter subscription: {ml.name}"[:255],
                    body=f"Clicked the double opt-in link sent after the form '{form.name if form else form_id}'"
                         f" on {now:%d %b %Y %H:%M} UTC" + (f" from {ip}" if ip else "") + ". Marketing consent recorded.",
                    contact_id=ct.id, account_id=ct.account_id, owner_id=ct.owner_id, completed_at=now))
    for sub in db.scalars(select(FormSubmission).where(FormSubmission.form_id == form_id,
                                                       FormSubmission.contact_id == ct.id,
                                                       FormSubmission.status == "pending")):
        sub.status = "confirmed"
    db.commit()
    return "confirmed", form, ml


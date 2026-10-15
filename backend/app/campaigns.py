"""Campaigns and newsletters: merge fields, audience, personalised rendering, tracking, unsubscribe and the send queue.

Sending is done by the scheduler (app.jobs) in small batches at CRM_BULK_RATE_PER_MINUTE, so a large campaign
keeps going in the background and survives restarts: every recipient row is queued, then sent, failed or skipped.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import html
import re
import secrets
from collections import Counter
from urllib.parse import quote

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from . import mail
from .config import get_settings
from .models import Account, Activity, Campaign, CampaignRecipient, Contact, ListMember, MailingList, User

MERGE = re.compile(r"\{([a-z_]+)(?:\|([^{}]*))?\}")
MERGE_FIELDS = {
    "first_name": "First name", "last_name": "Last name", "full_name": "Full name", "email": "Email address",
    "company": "Company (account)", "job_title": "Job title", "country": "Country", "owner": "Contact owner",
    "unsubscribe_url": "Unsubscribe link (added automatically if missing)",
    "postal_address": "Your postal address (CRM_MARKETING_POSTAL_ADDRESS)",
}
SAMPLE = {"first_name": "Jane", "last_name": "Example", "full_name": "Jane Example", "email": "jane@example.com",
          "company": "Example Customer Ltd", "job_title": "Head of Infrastructure", "country": "France",
          "owner": "Your Name", "postal_address": ""}


# ---------------------------------------------------------------- merge fields
def contact_values(c: Contact, account: Account | None = None, owner: User | None = None) -> dict:
    account = account or c.account
    owner = owner or c.owner
    return {"first_name": c.first_name or "", "last_name": c.last_name or "", "full_name": c.full_name,
            "email": c.email or "", "company": account.name if account else "", "job_title": c.job_title or "",
            "country": c.country or (account.country if account and account.country else ""),
            "owner": owner.full_name if owner else ""}


def merge(text: str, values: dict, escape: bool = True) -> str:
    """Replace {field} and {field|fallback}. Values are HTML-escaped when merging into HTML; unknown fields stay."""
    def sub(m):
        name, fallback = m.group(1), m.group(2)
        if name not in values:
            return m.group(0)
        v = values[name] or (fallback or "")
        return html.escape(v) if escape and name not in ("unsubscribe_url",) else v
    return MERGE.sub(sub, text or "")


# ---------------------------------------------------------------- links
def _sign(*parts: str) -> str:
    key = get_settings().secret_key.encode()
    return hmac.new(key, "|".join(parts).encode(), hashlib.sha256).hexdigest()[:20]


def unsubscribe_url(token: str) -> str:
    return f"{get_settings().app_url}/api/public/unsubscribe/{token}"


def click_url(token: str, url: str) -> str:
    return f"{get_settings().app_url}/api/t/c/{token}?u={quote(url, safe='')}&s={_sign(token, url)}"


def valid_click(token: str, url: str, sig: str) -> bool:
    return hmac.compare_digest(_sign(token, url), sig or "")


HREF = re.compile(r'(<a\b[^>]*?\bhref=")(https?://[^"]+)(")', re.I)


def _footer(c: Campaign) -> str:
    s = get_settings()
    address = html.escape(s.marketing_postal_address) if s.marketing_postal_address else ""
    return ('<div style="font-family:Arial,sans-serif;font-size:12px;color:#888;text-align:center;padding:24px 12px">'
            f'{address + "<br>" if address else ""}'
            'You receive this email because you are in contact with us. '
            '<a href="{unsubscribe_url}" style="color:#888">Unsubscribe</a></div>')


def personalise(c: Campaign, values: dict, token: str, track: bool = True) -> tuple[str, str]:
    """Subject and HTML for one recipient: merge fields, preheader, unsubscribe footer, click and open tracking."""
    body = c.body_html or ""
    if "{unsubscribe_url}" not in body:  # every bulk email must let people opt out
        footer = _footer(c)
        body = re.sub(r"(?i)</body>", footer + "</body>", body, count=1) if re.search(r"(?i)</body>", body) \
            else body + footer
    values = {**values, "unsubscribe_url": unsubscribe_url(token),
              "postal_address": get_settings().marketing_postal_address}
    out = merge(body, values)
    if c.preheader:
        pre = ('<div style="display:none;max-height:0;overflow:hidden;opacity:0">'
               f"{html.escape(merge(c.preheader, values, escape=False))}</div>")
        out = re.sub(r"(?i)(<body[^>]*>)", lambda m: m.group(1) + pre, out, count=1) \
            if re.search(r"(?i)<body[^>]*>", out) else pre + out
    if track and c.track_clicks:
        unsub = unsubscribe_url(token)
        out = HREF.sub(lambda m: m.group(0) if html.unescape(m.group(2)) == unsub else
                       m.group(1) + html.escape(click_url(token, html.unescape(m.group(2)))) + m.group(3), out)
    if track and c.track_opens:
        pixel = (f'<img src="{get_settings().app_url}/api/t/o/{token}.gif" width="1" height="1" alt="" '
                 'style="display:block;border:0;width:1px;height:1px">')
        out = re.sub(r"(?i)</body>", pixel + "</body>", out, count=1) if re.search(r"(?i)</body>", out) \
            else out + pixel
    return merge(c.subject, values, escape=False), out


def build_message(c: Campaign, email: str, values: dict, token: str, track: bool = True) -> mail.Message:
    subject, body = personalise(c, values, token, track)
    s = get_settings()
    unsub = unsubscribe_url(token)
    return mail.Message(
        sender=mail.sender_for(s.mail_from, "bulk") or s.mail_from, to=[email], subject=subject, html=body,
        from_name=c.from_name or s.mail_from_name or None, reply_to=c.reply_to or None,
        headers={"List-Unsubscribe": f"<{unsub}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                 "X-CRM-Campaign": str(c.id)})


# ---------------------------------------------------------------- audience
def audience(db: Session, c: Campaign) -> tuple[list[tuple[Contact, str]], list[tuple[Contact | None, str, str]]]:
    """(contacts to send to, skipped (contact, email, reason)). One email per address, across all chosen lists."""
    lists = {ml.id: ml for ml in db.scalars(select(MailingList).where(MailingList.id.in_(c.list_ids or [])))}
    members = db.scalars(select(ListMember).options(
        selectinload(ListMember.contact).selectinload(Contact.account),
        selectinload(ListMember.contact).selectinload(Contact.owner))
        .where(ListMember.list_id.in_(list(lists)))).all()
    newsletter_ok = {m.contact_id for m in members if m.status == "subscribed" and lists[m.list_id].kind == "newsletter"}
    send: dict[str, Contact] = {}
    skipped: dict[int, tuple[Contact | None, str, str]] = {}
    for m in sorted(members, key=lambda m: m.contact_id):
        ct = m.contact
        if m.status != "subscribed":
            skipped.setdefault(ct.id, (ct, ct.email or "", "subscription not confirmed yet" if m.status == "pending"
                                       else "unsubscribed from the list"))
            continue
        email = (ct.email or "").strip().lower()
        if not email or "@" not in email:
            skipped[ct.id] = (ct, "", "no email address")
        elif ct.unsubscribed:
            skipped[ct.id] = (ct, email, "unsubscribed from all marketing email")
        elif c.require_consent and not ct.consent_marketing and ct.id not in newsletter_ok:
            skipped[ct.id] = (ct, email, "no marketing consent")
        elif email not in send:
            send[email] = ct
    sending_ids = {ct.id for ct in send.values()}
    return ([(ct, e) for e, ct in send.items()],
            [v for k, v in skipped.items() if k not in sending_ids])


def audience_summary(db: Session, c: Campaign) -> dict:
    to_send, skipped = audience(db, c)
    return {"recipients": len(to_send), "skipped": len(skipped),
            "skipped_by_reason": dict(Counter(r for _, _, r in skipped))}


def prepare(db: Session, c: Campaign) -> None:
    """Freeze the audience: one queued row per recipient (and skipped rows with the reason)."""
    if db.scalar(select(func.count()).select_from(CampaignRecipient).where(CampaignRecipient.campaign_id == c.id)):
        return
    to_send, skipped = audience(db, c)
    for ct, email in to_send:
        db.add(CampaignRecipient(campaign_id=c.id, contact_id=ct.id, email=email, token=secrets.token_urlsafe(24),
                                 status="queued"))
    for ct, email, reason in skipped:
        db.add(CampaignRecipient(campaign_id=c.id, contact_id=ct.id if ct else None, email=email or "-",
                                 token=secrets.token_urlsafe(24), status="skipped", reason=reason))
    c.status, c.started_at, c.last_error = "sending", dt.datetime.now(dt.UTC), None
    db.flush()


def send_batch(db: Session, c: Campaign, limit: int) -> int:
    """Send up to `limit` queued messages of a sending campaign. Returns how many were attempted."""
    rows = db.scalars(select(CampaignRecipient).options(
        selectinload(CampaignRecipient.contact).selectinload(Contact.account),
        selectinload(CampaignRecipient.contact).selectinload(Contact.owner))
        .where(CampaignRecipient.campaign_id == c.id, CampaignRecipient.status == "queued")
        .order_by(CampaignRecipient.id).limit(limit).with_for_update(skip_locked=True)).all()
    if not rows:
        c.status, c.finished_at = "sent", dt.datetime.now(dt.UTC)
        db.commit()
        return 0
    try:
        with mail.MailSession("bulk") as session:
            for r in rows:
                ct = r.contact
                if ct is None or ct.unsubscribed:  # unsubscribed since the campaign started
                    r.status, r.reason = "skipped", "unsubscribed"
                    continue
                try:
                    session.send(build_message(c, r.email, contact_values(ct), r.token))
                    r.status, r.sent_at = "sent", dt.datetime.now(dt.UTC)
                except mail.MailError as exc:
                    r.status, r.reason = "failed", str(exc)[:255]
    except mail.MailError as exc:  # could not connect at all: pause, keep the queue
        db.rollback()
        c = db.get(Campaign, c.id)
        c.status, c.last_error = "paused", str(exc)[:500]
        db.commit()
        return 0
    db.commit()
    return len(rows)


def process(db: Session, now: dt.datetime | None = None, interval_seconds: int = 30) -> int:
    """One scheduler tick: start due scheduled campaigns, then send the next batch of each sending campaign."""
    now = now or dt.datetime.now(dt.UTC)
    for c in db.scalars(select(Campaign).where(Campaign.status == "scheduled", Campaign.scheduled_at <= now)):
        prepare(db, c)
    db.commit()
    per_tick = max(1, get_settings().bulk_rate_per_minute * interval_seconds // 60)
    sent = 0
    for c in db.scalars(select(Campaign).where(Campaign.status == "sending").order_by(Campaign.id)).all():
        sent += send_batch(db, c, per_tick)
    return sent


def stats(db: Session, c: Campaign) -> dict:
    rows = db.execute(select(CampaignRecipient.status, func.count()).where(CampaignRecipient.campaign_id == c.id)
                      .group_by(CampaignRecipient.status)).all()
    by = dict(rows)
    q = select(func.count()).select_from(CampaignRecipient).where(CampaignRecipient.campaign_id == c.id)
    opened = db.scalar(q.where(CampaignRecipient.opened_at.is_not(None))) or 0
    clicked = db.scalar(q.where(CampaignRecipient.clicked_at.is_not(None))) or 0
    unsub = db.scalar(q.where(CampaignRecipient.unsubscribed_at.is_not(None))) or 0
    sent = by.get("sent", 0)
    return {"queued": by.get("queued", 0), "sent": sent, "failed": by.get("failed", 0),
            "skipped": by.get("skipped", 0), "opened": opened, "clicked": clicked, "unsubscribed": unsub,
            "open_rate": round(100 * opened / sent, 1) if sent else 0.0,
            "click_rate": round(100 * clicked / sent, 1) if sent else 0.0}


# ---------------------------------------------------------------- unsubscribe
def unsubscribe(db: Session, token: str) -> CampaignRecipient | None:
    r = db.scalar(select(CampaignRecipient).where(CampaignRecipient.token == token))
    if not r or r.contact_id is None:
        return r
    now = dt.datetime.now(dt.UTC)
    ct = db.get(Contact, r.contact_id)
    if not ct.unsubscribed:
        ct.unsubscribed = True
        for m in db.scalars(select(ListMember).where(ListMember.contact_id == ct.id, ListMember.status == "subscribed")):
            m.status, m.unsubscribed_at = "unsubscribed", now
        c = db.get(Campaign, r.campaign_id)
        db.add(Activity(type="note", subject="Unsubscribed from marketing email",
                        body=f"Clicked unsubscribe in '{c.name if c else 'a campaign'}'", contact_id=ct.id,
                        account_id=ct.account_id, completed_at=now))
    r.unsubscribed_at = r.unsubscribed_at or now
    db.commit()
    return r

"""Website tracking: the script websites embed, what it reports (page views, custom events, visitors identified by
email), how visits are attributed (source, medium, campaign) and the statistics shown in the CRM.

Privacy choices: page addresses are kept without their query string (it may carry personal data; the campaign
parameters are kept with the visit instead); IP addresses are not stored; the script honours Do Not Track / Global Privacy Control and can wait
for the visitor's consent; automatically captured forms only send the fields the CRM knows (email, name, company...)."""
from __future__ import annotations

import datetime as dt
import json
import re
import secrets
from collections import Counter
from functools import lru_cache
from pathlib import Path
from urllib.parse import SplitResult, parse_qsl, urlsplit

from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import webforms as wf
from .config import get_settings
from .models import Activity, Contact, TrackingSite, WebEvent, WebVisitor

UTM = ("utm_source", "utm_medium", "utm_campaign")
PARAMS = ("utm_term", "utm_content", "gclid", "gbraid", "wbraid", "fbclid", "msclkid", "li_fat_id")
SEARCH = {"google": "google", "bing": "bing", "duckduckgo": "duckduckgo", "yahoo": "yahoo", "qwant": "qwant",
          "ecosia": "ecosia", "baidu": "baidu", "yandex": "yandex", "brave": "brave"}
SOCIAL = {"linkedin.com": "linkedin", "lnkd.in": "linkedin", "twitter.com": "twitter", "t.co": "twitter",
          "x.com": "twitter", "facebook.com": "facebook", "fb.com": "facebook", "youtube.com": "youtube",
          "reddit.com": "reddit", "instagram.com": "instagram", "github.com": "github"}
ID = re.compile(r"^[A-Za-z0-9-]{8,40}$")
HOST = re.compile(r"^(?=.*[a-z])[a-z0-9-]+(\.[a-z0-9-]+)*$")
MAX_BODY = 32_000
SESSION_MINUTES = 30
identify_limiter = wf.IpLimiter(limit=20, window=3600)  # contacts created or updated per address
collect_limiter = wf.IpLimiter(limit=600, window=600)


# ---------------------------------------------------------------- the payload the script sends
class Event(BaseModel):
    t: str = Field(pattern="^(page|event|identify)$")
    url: str | None = Field(None, max_length=4000)
    title: str | None = Field(None, max_length=500)
    ref: str | None = Field(None, max_length=4000)
    name: str | None = Field(None, max_length=255)
    props: dict = Field(default_factory=dict)
    fields: dict = Field(default_factory=dict)
    form: str | None = Field(None, max_length=255)


class Batch(BaseModel):
    vid: str = Field(pattern=ID.pattern)
    sid: str = Field(pattern=ID.pattern)
    new_session: bool = False
    events: list[Event] = Field(default_factory=list, max_length=20)


# ---------------------------------------------------------------- sites
def _split(url: str | None) -> SplitResult:
    """urlsplit that never raises: addresses come from browsers and may be malformed."""
    try:
        parts = urlsplit(url or "")
        parts.hostname  # noqa: B018 - raises on a malformed host
        return parts
    except ValueError:
        return urlsplit("")


def new_key() -> str:
    return secrets.token_urlsafe(18)[:24]


def normalize_domain(value: str) -> str | None:
    """'https://www.metricshub.com/contact' -> 'www.metricshub.com'. Subdomains of a domain are allowed too."""
    v = value.strip().lower()
    if not v:
        return None
    try:
        host = (urlsplit(v if "//" in v else f"//{v}").hostname or "").rstrip(".")
    except ValueError:
        return None
    return host if HOST.match(host) else None


def host_allowed(site: TrackingSite, url: str | None) -> bool:
    host = _split(url).hostname
    if not host:
        return False
    host = host.lower().rstrip(".")
    return any(host == d or host.endswith(f".{d}") for d in (site.domains or []))


def script_url(site: TrackingSite) -> str:
    return f"{get_settings().app_url.rstrip('/')}/api/public/t/{site.key}.js"


def snippet(site: TrackingSite) -> str:
    return f'<script src="{script_url(site)}" async></script>'


@lru_cache
def _template() -> str:
    return (Path(__file__).parent / "assets" / "tracker.js").read_text(encoding="utf-8")


def script(site: TrackingSite) -> str:
    config = {"endpoint": f"{get_settings().app_url.rstrip('/')}/api/public/t/{site.key}/collect",
              "utm": site.track_utm, "params": site.track_params, "forms": site.capture_forms,
              "consent": site.require_consent, "dnt": site.respect_dnt, "session_minutes": SESSION_MINUTES}
    # "</" cannot end the script early: the JSON is embedded in JavaScript, not HTML, but stay safe
    return _template().replace("__CONFIG__", json.dumps(config).replace("</", "<\\/"))


# ---------------------------------------------------------------- attribution
def clean_url(url: str | None) -> str | None:
    """The address without its query string and fragment."""
    if not url:
        return None
    parts = _split(url)
    if parts.scheme not in ("http", "https"):
        return None
    return f"{parts.scheme}://{parts.netloc}{parts.path or '/'}"[:1000]


def touch(site: TrackingSite, url: str | None, referrer: str | None) -> dict:
    """Where a visit came from. Campaign parameters win; otherwise the referrer decides (search engine, social
    network, another site), and no referrer (or one from the site itself) is direct."""
    query = dict(parse_qsl(_split(url).query))
    t: dict = {"landing": clean_url(url)}
    ref_host = (_split(referrer).hostname or "").lower()
    internal = bool(ref_host) and host_allowed(site, referrer)
    if referrer and not internal:
        t["referrer"] = clean_url(referrer)
    if site.track_utm and any(query.get(k) for k in UTM):
        t.update(source=query.get("utm_source"), medium=query.get("utm_medium"), campaign=query.get("utm_campaign"))
    elif query.get("gclid") or query.get("gbraid") or query.get("wbraid"):
        t.update(source="google", medium="cpc")
    elif query.get("msclkid"):
        t.update(source="bing", medium="cpc")
    elif ref_host and not internal:
        name = ref_host.removeprefix("www.")
        engine = next((v for k, v in SEARCH.items() if re.search(rf"(^|\.){k}\.", name + ".")), None)
        social = next((v for k, v in SOCIAL.items() if name == k or name.endswith("." + k)), None)
        t.update(source=engine or social or name, medium="organic" if engine else "social" if social else "referral")
    else:
        t.update(source="direct", medium="none")
    if site.track_params:
        t.update({k: query[k][:255] for k in PARAMS if query.get(k)})
    return {k: (v[:255] if isinstance(v, str) else v) for k, v in t.items() if v}


def _direct(t: dict) -> bool:
    return t.get("source") in (None, "direct")


# ---------------------------------------------------------------- collecting
def collect(db: Session, site: TrackingSite, batch: Batch, *, user_agent: str | None = None,
            ip: str | None = None) -> dict:
    """Store a batch from the script. Returns what happened (for tests and logs)."""
    now = dt.datetime.now(dt.UTC)
    v = db.scalar(select(WebVisitor).where(WebVisitor.site_id == site.id, WebVisitor.vid == batch.vid))
    if v is None:
        v = WebVisitor(site_id=site.id, vid=batch.vid, first_seen=now, sessions=0, page_views=0, first_touch={},
                       last_touch={})
        db.add(v)
        db.flush()
    v.last_seen = now
    v.user_agent = (user_agent or "")[:255] or v.user_agent
    result = {"stored": 0, "identified": None}
    pages = [e for e in batch.events if e.t == "page"]
    if batch.new_session or not v.sessions:
        v.sessions += 1
        landing = pages[0] if pages else (batch.events[0] if batch.events else None)
        t = touch(site, landing.url, landing.ref) if landing else {}
        if t and not v.first_touch:
            v.first_touch = t
        if t and (not _direct(t) or not v.last_touch):
            v.last_touch = t
            if v.contact_id:
                _attribute(db.get(Contact, v.contact_id), v)
    for e in batch.events:
        url = clean_url(e.url)  # the campaign parameters are kept with the visit (touch), not on each page
        if e.t == "identify":
            if not identify_limiter.allow(ip):
                continue
            ct = identify(db, site, v, e, url)
            if ct is None:
                continue
            result["identified"] = ct.id
            name = "Form submitted" if e.form else "Identified"
            props = {"form": e.form[:255]} if e.form else {}
        elif e.t == "event":
            if not (e.name or "").strip():
                continue
            name, props = e.name.strip()[:255], _props(e.props)
        else:
            v.page_views += 1
            name, props = (e.title or "").strip()[:255] or None, {}
        db.add(WebEvent(site_id=site.id, visitor_id=v.id, contact_id=v.contact_id, session=batch.sid, kind=e.t,
                        name=name, url=url, referrer=clean_url(e.ref) if e.t == "page" else None, props=props,
                        created_at=now))
        result["stored"] += 1
    if pages:
        site.last_hit_at, site.last_hit_url = now, clean_url(pages[-1].url)
    db.flush()
    return result


def _props(props: dict) -> dict:
    """Custom event properties: up to 30 simple values."""
    out = {}
    for k, val in list(props.items())[:30]:
        if isinstance(val, (str, int, float, bool)) or val is None:
            out[str(k)[:60]] = val[:500] if isinstance(val, str) else val
    return out


def identify(db: Session, site: TrackingSite, v: WebVisitor, e: Event, url: str | None) -> Contact | None:
    """Link the visitor to the contact with this email (created if new). Only the fields the CRM knows are read:
    email, names, phone, job title, company, country, LinkedIn, and a marketing consent checkbox."""
    values: dict[str, str] = {}
    for k, val in wf.clean(e.fields).items():
        target = wf.ALIASES.get(wf.norm_key(k))
        if target and val and target not in values:
            values[target] = val
    email = (values.get("email") or "").strip().lower()
    if not wf.EMAIL.match(email) or len(email) > 255:
        return None
    ct, created = wf.upsert_contact(db, email, values, lead_source=site.lead_source, brand_id=site.brand_id,
                                    owner_id=site.owner_id)
    if wf.is_true(values.get("consent")) and not ct.unsubscribed and not ct.consent_marketing:
        ct.consent_marketing, ct.consent_at = True, dt.datetime.now(dt.UTC)
    if v.contact_id != ct.id:
        v.contact_id = ct.id
        # earlier anonymous visits of this browser now belong to the contact
        db.execute(update(WebEvent).where(WebEvent.visitor_id == v.id, WebEvent.contact_id.is_(None))
                   .values(contact_id=ct.id))
        where = f" (form on {urlsplit(url).path or '/'})" if e.form and url else ""
        body = f"{'New contact. ' if created else ''}Identified on {site.name}{where}."
        if src := _describe(v.first_touch):
            body += f" First came from {src}."
        db.add(Activity(type="note", subject=f"Website: {site.name}"[:255], body=body, contact_id=ct.id,
                        account_id=ct.account_id, owner_id=ct.owner_id, completed_at=dt.datetime.now(dt.UTC)))
    _attribute(ct, v)
    db.flush()
    return ct


def _describe(t: dict) -> str:
    if not t or _direct(t):
        return ""
    s = f"{t.get('source')} / {t.get('medium')}"
    return s + (f" (campaign {t['campaign']})" if t.get("campaign") else "")


def _attribute(ct: Contact | None, v: WebVisitor) -> None:
    """Original source: the first touch ever seen for the contact. Latest: the last visit that came from somewhere."""
    if ct is None:
        return
    web = dict((ct.extra or {}).get("web") or {})
    if v.first_touch and not web.get("original"):
        web["original"] = v.first_touch
    if v.last_touch and (not _direct(v.last_touch) or not web.get("latest")):
        web["latest"] = v.last_touch
    ct.extra = {**(ct.extra or {}), "web": web}


# ---------------------------------------------------------------- reading
def contact_activity(db: Session, contact: Contact, limit: int = 100) -> dict:
    visitors = db.scalars(select(WebVisitor).where(WebVisitor.contact_id == contact.id)).all()
    events = db.scalars(select(WebEvent).where(WebEvent.contact_id == contact.id)
                        .order_by(WebEvent.created_at.desc(), WebEvent.id.desc()).limit(limit)).all()
    pages = Counter(e.url for e in events if e.kind == "page" and e.url)
    web = (contact.extra or {}).get("web") or {}
    return {
        "tracked": bool(visitors),
        "first_seen": min((v.first_seen for v in visitors), default=None),
        "last_seen": max((v.last_seen for v in visitors), default=None),
        "sessions": sum(v.sessions for v in visitors), "page_views": sum(v.page_views for v in visitors),
        "browsers": len(visitors), "original": web.get("original"), "latest": web.get("latest"),
        "top_pages": [{"url": u, "views": n} for u, n in pages.most_common(5)],
        "events": [{"kind": e.kind, "name": e.name, "url": e.url, "props": e.props, "at": e.created_at,
                    "session": e.session} for e in events],
    }


def overview(db: Session, site: TrackingSite, days: int = 30) -> dict:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    ev = select(WebEvent).where(WebEvent.site_id == site.id, WebEvent.created_at >= since)
    count = lambda stmt: db.scalar(stmt) or 0  # noqa: E731
    page = WebEvent.kind == "page"
    by = lambda col, *where: db.execute(  # noqa: E731
        select(col, func.count()).where(WebEvent.site_id == site.id, WebEvent.created_at >= since, *where)
        .group_by(col).order_by(func.count().desc()).limit(10)).all()
    visitors = db.scalars(select(WebVisitor).where(WebVisitor.site_id == site.id, WebVisitor.last_seen >= since)).all()
    sources = Counter(f"{v.first_touch.get('source', 'direct')} / {v.first_touch.get('medium', 'none')}"
                      for v in visitors)
    recent = db.execute(
        select(Contact.id, Contact.first_name, Contact.last_name, Contact.email, WebVisitor.last_seen,
               WebVisitor.page_views, WebVisitor.first_touch)
        .join(WebVisitor, WebVisitor.contact_id == Contact.id)
        .where(WebVisitor.site_id == site.id).order_by(WebVisitor.last_seen.desc()).limit(10)).all()
    return {
        "days": days,
        "visitors": len(visitors),
        "identified": sum(1 for v in visitors if v.contact_id),
        "page_views": count(select(func.count()).select_from(ev.where(page).subquery())),
        "sessions": count(select(func.count(func.distinct(WebEvent.session))).where(
            WebEvent.site_id == site.id, WebEvent.created_at >= since)),
        "events": count(select(func.count()).select_from(ev.where(WebEvent.kind == "event").subquery())),
        "top_pages": [{"url": u, "views": n} for u, n in by(WebEvent.url, page)],
        "top_events": [{"name": u, "count": n} for u, n in by(WebEvent.name, WebEvent.kind == "event")],
        "top_sources": [{"source": s, "visitors": n} for s, n in sources.most_common(10)],
        "recent_contacts": [{"id": r[0], "name": " ".join(p for p in (r[1], r[2]) if p) or r[3], "email": r[3],
                             "last_seen": r[4], "page_views": r[5], "source": _describe(r[6]) or "direct"}
                            for r in recent],
        "last_hit_at": site.last_hit_at, "last_hit_url": site.last_hit_url,
    }


def prune(db: Session, days: int) -> int:
    """Forget events older than `days`, and anonymous visitors not seen since then. The caller commits."""
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    n = db.query(WebEvent).filter(WebEvent.created_at < since).delete(synchronize_session=False)
    db.query(WebVisitor).filter(WebVisitor.last_seen < since, WebVisitor.contact_id.is_(None)).delete(
        synchronize_session=False)
    db.flush()
    return n

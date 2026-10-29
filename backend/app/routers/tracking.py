"""Website tracking settings (administrators), statistics, and a contact's website activity."""
import datetime as dt
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import tracking
from ..crud import get_or_404
from ..db import get_db
from ..models import Contact, TrackingSite, User
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api", tags=["website tracking"])


class SiteIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    domains: list[str] = []
    brand_id: int | None = None
    owner_id: int | None = None
    lead_source: str = Field("website_contact", max_length=40)
    track_utm: bool = True
    track_params: bool = False
    capture_forms: bool = True
    require_consent: bool = False
    respect_dnt: bool = True
    active: bool = True

    @field_validator("domains")
    @classmethod
    def hosts(cls, v: list[str]) -> list[str]:
        out = []
        for d in v:
            host = tracking.normalize_domain(d)
            if not host:
                raise ValueError(f"Not a domain: {d!r}")
            if host not in out:
                out.append(host)
        return out


class SiteUpdate(SiteIn):
    name: str | None = Field(None, min_length=1, max_length=120)  # type: ignore[assignment]


class SiteOut(SiteIn):
    model_config = {"from_attributes": True}
    id: int
    key: str
    snippet: str = ""
    script_url: str = ""
    last_hit_at: dt.datetime | None
    last_hit_url: str | None


def _out(site: TrackingSite) -> SiteOut:
    o = SiteOut.model_validate(site)
    o.snippet, o.script_url = tracking.snippet(site), tracking.script_url(site)
    return o


@router.get("/tracking/sites", response_model=list[SiteOut])
def list_sites(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return [_out(s) for s in db.scalars(select(TrackingSite).order_by(TrackingSite.id))]


@router.post("/tracking/sites", response_model=SiteOut, status_code=201)
def create_site(data: SiteIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    site = TrackingSite(key=tracking.new_key(), **data.model_dump())
    db.add(site)
    db.commit()
    db.refresh(site)
    return _out(site)


@router.patch("/tracking/sites/{site_id}", response_model=SiteOut)
def update_site(site_id: int, data: SiteUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    site = get_or_404(db, TrackingSite, site_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        if v is not None or k in ("brand_id", "owner_id"):
            setattr(site, k, v)
    db.commit()
    db.refresh(site)
    return _out(site)


@router.delete("/tracking/sites/{site_id}", status_code=204)
def delete_site(site_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Deletes the site with its visitors and events. Contacts and their timelines stay."""
    db.delete(get_or_404(db, TrackingSite, site_id))
    db.commit()


@router.get("/tracking/sites/{site_id}/overview")
def site_overview(site_id: int, days: int = Query(30, ge=1, le=400), db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    return tracking.overview(db, get_or_404(db, TrackingSite, site_id), days)


def _public_host(host: str) -> bool:
    """The integration check fetches pages on the server: only public addresses, never the CRM's own network."""
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return False
    return bool(addresses) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addresses)


def _fetch(url: str) -> httpx.Response:
    with httpx.Client(timeout=10, follow_redirects=False, headers={"User-Agent": "MetricsHub-CRM integration check"}) \
            as client:
        for _ in range(5):
            host = urlsplit(url).hostname or ""
            if urlsplit(url).scheme not in ("http", "https") or not _public_host(host):
                raise ValueError(f"{host or url} is not a public web address")
            r = client.get(url)
            if r.is_redirect and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            return r
    raise ValueError("Too many redirects")


class CheckIn(BaseModel):
    url: str | None = Field(None, max_length=1000)


@router.post("/tracking/sites/{site_id}/check")
def check_integration(site_id: int, data: CheckIn | None = None, db: Session = Depends(get_db),
                      _: User = Depends(require_admin)):
    """Look for the tracking code in the home page of each domain (or the page given), and report the last hit."""
    site = get_or_404(db, TrackingSite, site_id)
    urls = [data.url] if data and data.url else [f"https://{d}/" for d in site.domains]
    results = []
    for url in urls:
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        try:
            r = _fetch(url)
            found = f"/api/public/t/{site.key}.js" in r.text
            results.append({"url": url, "status": r.status_code, "found": found,
                            "message": "Tracking code found" if found else "Tracking code not found on this page"})
        except (httpx.HTTPError, ValueError) as exc:
            results.append({"url": url, "status": None, "found": False, "message": f"Could not load the page: {exc}"})
    return {"results": results, "last_hit_at": site.last_hit_at, "last_hit_url": site.last_hit_url,
            "domains_ok": bool(site.domains)}


@router.get("/contacts/{contact_id}/web")
def contact_web_activity(contact_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Pages viewed, custom events and forms on tracked websites, with where the contact came from."""
    return tracking.contact_activity(db, get_or_404(db, Contact, contact_id))

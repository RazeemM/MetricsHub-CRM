"""Public endpoints reached from emails (no login): unsubscribe, open pixel, click redirect."""
import base64
import datetime as dt
import html

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import campaigns as cmp
from ..db import get_db
from ..models import CampaignRecipient

router = APIRouter(tags=["public"])
PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
NO_STORE = {"Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer"}


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>{html.escape(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f2f4f7;color:#1f2933;margin:0;padding:48px 16px}}
.card{{max-width:440px;margin:auto;background:#fff;border-radius:10px;padding:28px;box-shadow:0 2px 10px #0001}}
button{{background:#1f2933;color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:15px;cursor:pointer}}
</style></head><body><div class="card">{body}</div></body></html>""", headers=NO_STORE)


@router.get("/api/public/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe_page(token: str, db: Session = Depends(get_db)):
    """A confirmation page: a GET must not unsubscribe, because mail scanners follow links."""
    r = db.scalar(select(CampaignRecipient).where(CampaignRecipient.token == token))
    if token != "test" and not r:
        return _page("Link expired", "<h2>This link is no longer valid</h2>")
    if r and r.unsubscribed_at:
        return _page("Unsubscribed", "<h2>You are unsubscribed</h2><p>You will not receive our marketing emails.</p>")
    email = html.escape(r.email) if r else "you@example.com"
    return _page("Unsubscribe", f"""<h2>Unsubscribe</h2>
<p>Stop sending marketing emails to <b>{email}</b>?</p>
<form method="post"><button type="submit">Unsubscribe</button></form>""")


@router.post("/api/public/unsubscribe/{token}", response_class=HTMLResponse)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    """Confirmation form, and RFC 8058 one-click unsubscribe from mail clients (List-Unsubscribe-Post)."""
    if token == "test":
        return _page("Test", "<h2>Test email</h2><p>Unsubscribe works; nothing was changed.</p>")
    if not cmp.unsubscribe(db, token):
        raise HTTPException(404, "Unknown link")
    return _page("Unsubscribed", "<h2>You are unsubscribed</h2><p>You will not receive our marketing emails anymore."
                                 "</p>")


@router.get("/api/t/o/{token}.gif")
def open_pixel(token: str, db: Session = Depends(get_db)):
    r = db.scalar(select(CampaignRecipient).where(CampaignRecipient.token == token))
    if r:
        r.opened_at = r.opened_at or dt.datetime.now(dt.UTC)
        r.open_count += 1
        db.commit()
    return Response(PIXEL, media_type="image/gif", headers=NO_STORE)


@router.get("/api/t/c/{token}")
def click(token: str, u: str, s: str, db: Session = Depends(get_db)):
    # only links signed when the email was built are followed: no open redirect
    if not cmp.valid_click(token, u, s) or not u.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid link")
    r = db.scalar(select(CampaignRecipient).where(CampaignRecipient.token == token))
    if r:
        now = dt.datetime.now(dt.UTC)
        r.clicked_at = r.clicked_at or now
        r.opened_at = r.opened_at or now  # a click proves the email was opened (images may be blocked)
        r.click_count += 1
        db.commit()
    return RedirectResponse(u, status_code=302, headers=NO_STORE)

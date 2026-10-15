"""Public endpoints (no login): unsubscribe, open pixel, click redirect, website forms and their opt-in link."""
import base64
import datetime as dt
import html
import json
from urllib.parse import parse_qsl

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import campaigns as cmp
from .. import webforms as wf
from ..config import get_settings
from ..db import get_db
from ..models import CampaignRecipient, WebForm

router = APIRouter(tags=["public"])
PIXEL = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
NO_STORE = {"Cache-Control": "no-store, private", "Referrer-Policy": "no-referrer"}


def _page(title: str, body: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport"
content="width=device-width,initial-scale=1"><meta name="robots" content="noindex"><title>{html.escape(title)}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;background:#f2f4f7;color:#1f2933;margin:0;padding:48px 16px}}
.card{{max-width:440px;margin:auto;background:#fff;border-radius:10px;padding:28px;box-shadow:0 2px 10px #0001}}
button{{background:#1f2933;color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:15px;cursor:pointer}}
</style></head><body><div class="card">{body}</div></body></html>""", status_code=status_code, headers=NO_STORE)


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


# ---------------------------------------------------------------- website forms
MAX_BODY = 64_000


def client_ip(request: Request) -> str | None:
    """The visitor's address: X-Forwarded-For as written by the CRM_PROXY_HOPS proxies in front of the API."""
    hops = get_settings().proxy_hops
    xff = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if hops > 0 and xff:
        return (xff[-hops] if len(xff) >= hops else xff[0])[:45]
    return request.client.host if request.client else None


async def _fields(request: Request, body: bytes) -> dict:
    ctype = request.headers.get("content-type", "").lower()
    if "application/json" in ctype:
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            raise HTTPException(400, "Invalid JSON") from None
        if not isinstance(data, dict):
            raise HTTPException(400, "Send a JSON object of form fields")
        return data
    if "multipart/form-data" in ctype:
        form = await request.form()
        return {k: v for k, v in form.multi_items() if isinstance(v, str)}
    return dict(parse_qsl(body.decode("utf-8", errors="replace"), keep_blank_values=True))


def _wants_html(request: Request) -> bool:
    """A plain HTML form post (the browser navigates), as opposed to fetch() or a server calling the API."""
    ctype = request.headers.get("content-type", "").lower()
    return ("form" in ctype and "text/html" in request.headers.get("accept", "")
            and not request.headers.get("x-requested-with"))


@router.post("/api/public/forms/{key}")
async def submit_form(key: str, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """A website form submission. Authenticated by the form's secret: an HMAC signature (server to server) or the
    form token (browser). Answers JSON, or redirects a plain HTML form post to the form's thank-you page."""
    body = await request.body()
    data = await _fields(request, body) if len(body) <= MAX_BODY else {}
    # the database work is synchronous: keep it off the event loop
    return await run_in_threadpool(_submit, key, request, body, data, background, db)


def _submit(key: str, request: Request, body: bytes, data: dict, background: BackgroundTasks, db: Session):
    as_html = _wants_html(request)

    def fail(status: int, message: str):
        if as_html:
            return _page("Sorry", f"<h2>Sorry</h2><p>{html.escape(message)}</p>", status)
        return JSONResponse({"ok": False, "detail": message}, status_code=status, headers=NO_STORE)

    ip = client_ip(request)
    if not wf.limiter.allow(ip):
        return fail(429, "Too many requests, please try again later")
    if len(body) > MAX_BODY:
        return fail(413, "Submission too large")
    form = db.scalar(select(WebForm).where(WebForm.key == key))
    if not form or not form.active:
        return fail(404, "Unknown form")
    if not wf.origin_allowed(form, request.headers.get("origin")):
        return fail(403, "This website may not post to this form")
    if reason := wf.authenticate(form, request.headers, body, wf.clean(data)):
        return fail(401, reason)
    if wf.over_form_limit(db, form, ip):
        return fail(429, "Too many submissions, please try again later")
    sub = wf.submit(db, form, data, ip=ip, user_agent=request.headers.get("user-agent"),
                    page=request.headers.get("referer"))
    db.commit()
    if sub.status == "error":
        return fail(422, sub.note or "Invalid submission")
    if sub.status == "pending":
        background.add_task(wf.send_confirmation, sub.id)
    # spam gets the same answer as a real submission, so bots learn nothing
    status = "pending_confirmation" if sub.status == "pending" else "accepted"
    if as_html:
        if form.redirect_url:
            return RedirectResponse(form.redirect_url, status_code=303, headers=NO_STORE)
        msg = "Please check your inbox to confirm your subscription." if status == "pending_confirmation"             else "We received your message and will get back to you soon."
        return _page("Thank you", f"<h2>Thank you</h2><p>{msg}</p>")
    return JSONResponse({"ok": True, "status": status}, headers=NO_STORE)


@router.get("/api/public/confirm/{token}", response_class=HTMLResponse)
def confirm_page(token: str):
    """A page with a button: a GET must not subscribe anyone, because mail scanners follow links."""
    if not wf.read_token(token):
        return _page("Link expired", "<h2>This link is no longer valid</h2><p>Please sign up again on our website.</p>")
    return _page("Confirm your subscription", """<h2>Confirm your subscription</h2>
<p>Click to confirm that you want to receive our newsletter.</p>
<form method="post"><button type="submit">Confirm my subscription</button></form>""")


@router.post("/api/public/confirm/{token}", response_class=HTMLResponse)
def confirm_subscription(token: str, request: Request, db: Session = Depends(get_db)):
    outcome, form, ml = wf.confirm(db, token, ip=client_ip(request))
    if outcome == "invalid":
        return _page("Link expired", "<h2>This link is no longer valid</h2><p>Please sign up again on our website.</p>",
                     400)
    if form and form.confirm_redirect_url:
        return RedirectResponse(form.confirm_redirect_url, status_code=303, headers=NO_STORE)
    name = html.escape(ml.name) if ml else "our newsletter"
    return _page("Subscribed", f"<h2>You are subscribed</h2><p>Thank you for confirming your subscription to "
                               f"<b>{name}</b>.</p>")

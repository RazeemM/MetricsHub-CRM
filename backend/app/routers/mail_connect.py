"""Email sender settings, and Microsoft 365 sign-ins for sending email (CRM_MAIL_BACKEND=graph_delegated).

Connecting: POST /api/mail/microsoft/connect -> Microsoft sign-in (MFA) -> /api/mail/microsoft/callback, which keeps
the refresh token (encrypted) and sends the browser back to the page the user came from. Register
{CRM_APP_URL}/api/mail/microsoft/callback as a Web redirect URI of the app registration.
"""
import base64
import datetime as dt
import hashlib
import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import mail
from ..config import get_settings
from ..crud import audit
from ..db import get_db
from ..models import AppSetting, MailConnection, User
from ..security import ALGORITHM, get_current_user, require_admin

router = APIRouter(prefix="/api/mail", tags=["email"])
log = logging.getLogger("crm.mail")
STATE_COOKIE = "crm_mail_state"
COOKIE_PATH = "/api/mail/microsoft"


def callback_url() -> str:
    return f"{get_settings().app_url.rstrip('/')}/api/mail/microsoft/callback"


def _connection_out(conn: MailConnection | None, user: User) -> dict:
    st = mail.status()
    service = mail.sender_settings()["service_user_id"]
    return {
        "required": st["delegated"], "enabled": st["enabled"], "sender": mail.mail_from() or None,
        "connected": conn is not None, "account": conn.account if conn else None,
        "connected_at": conn.connected_at if conn else None, "last_used_at": conn.last_used_at if conn else None,
        "last_error": conn.last_error if conn else None,
        "used_for_automatic": conn is not None and service == user.id,
        "redirect_uri": callback_url() if user.role == "admin" else None,
    }


@router.get("/microsoft/connection")
def my_connection(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The signed-in user's Microsoft 365 connection for sending email."""
    return _connection_out(db.get(MailConnection, user.id), user)


class ConnectIn(BaseModel):
    return_to: str = Field(default="/", max_length=500)


@router.post("/microsoft/connect")
def connect(data: ConnectIn, request: Request, user: User = Depends(get_current_user)):
    """The Microsoft sign-in URL for the browser to open (authorization code flow with PKCE)."""
    s = get_settings()
    client_id, secret = mail.graph_credentials()
    tenant = mail.tenant_for(mail.mail_from() or user.email)
    if not (client_id and secret and tenant):
        raise HTTPException(503, "Microsoft 365 is not set up: CRM_GRAPH_CLIENT_ID, CRM_GRAPH_CLIENT_SECRET and "
                                 "CRM_GRAPH_TENANT_ID (or the SSO app registration)")
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    back = data.return_to if data.return_to.startswith("/") and not data.return_to.startswith("//") else "/"
    params = {
        "client_id": client_id, "response_type": "code", "redirect_uri": callback_url(),
        "scope": s.graph_delegated_scopes, "state": state, "code_challenge": challenge,
        "code_challenge_method": "S256", "prompt": "select_account", "response_mode": "query",
    }
    if user.email:
        params["login_hint"] = user.email
    cookie = jwt.encode({"state": state, "verifier": verifier, "uid": user.id, "tenant": tenant, "back": back,
                         "exp": int(time.time()) + 600}, s.secret_key, algorithm=ALGORITHM)
    resp = JSONResponse({"url": f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?"
                                f"{urlencode(params)}"})
    resp.set_cookie(STATE_COOKIE, cookie, max_age=600, httponly=True, samesite="lax", path=COOKIE_PATH,
                    secure=request.url.scheme == "https" or s.app_url.startswith("https://"))
    return resp


def _back(path: str, **query: str) -> RedirectResponse:
    sep = "&" if "?" in path else "?"
    resp = RedirectResponse(f"{get_settings().app_url.rstrip('/')}{path}{sep}{urlencode(query)}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path=COOKIE_PATH)
    return resp


@router.get("/microsoft/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
             error_description: str | None = None, db: Session = Depends(get_db)):
    s = get_settings()
    try:
        saved = jwt.decode(request.cookies.get(STATE_COOKIE, ""), s.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return _back("/", microsoft365_error="The Microsoft sign-in took too long, please try again")
    back = saved.get("back") or "/"
    if error:
        return _back(back, microsoft365_error=(error_description or error).split("\r\n")[0][:300])
    if not code or not state or not secrets.compare_digest(state, saved["state"]):
        return _back(back, microsoft365_error="Invalid sign-in state, please try again")
    user = db.get(User, saved["uid"])
    if not user or not user.is_active:
        return _back(back, microsoft365_error="Your CRM account is disabled")
    client_id, secret = mail.graph_credentials()
    try:
        with mail._client() as c:
            r = c.post(mail.token_endpoint(saved["tenant"]), data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": callback_url(),
                "client_id": client_id, "client_secret": secret, "code_verifier": saved["verifier"],
                "scope": s.graph_delegated_scopes})
    except httpx.HTTPError as exc:
        log.error("Microsoft 365 token exchange failed: %r", exc)
        return _back(back, microsoft365_error=f"The CRM server cannot reach Microsoft ({type(exc).__name__})")
    if r.status_code != 200:
        log.warning("Microsoft 365 connection refused for %s: %s", user.email, mail._error(r))
        return _back(back, microsoft365_error=f"Microsoft refused the connection: {mail._error(r)}"[:400])
    body = r.json()
    if not body.get("refresh_token"):
        return _back(back, microsoft365_error="Microsoft returned no refresh token: the app needs the "
                                              "offline_access permission")
    # the id token comes straight from Microsoft's token endpoint over TLS: its claims identify the account
    claims = jwt.decode(body["id_token"], options={"verify_signature": False}) if body.get("id_token") else {}
    account = (claims.get("preferred_username") or claims.get("upn") or claims.get("email") or user.email).lower()
    conn = db.get(MailConnection, user.id) or MailConnection(user_id=user.id)
    conn.account, conn.refresh_token, conn.scopes = account[:255], mail.seal(body["refresh_token"]), \
        (body.get("scope") or "")[:500]
    conn.connected_at, conn.last_error = dt.datetime.now(dt.UTC), None
    db.add(conn)
    audit(db, user, "mail_connection", user.id, "connect", {"account": account})
    db.commit()
    mail.forget_user_token(user.id)
    return _back(back, microsoft365="connected")


@router.delete("/microsoft/connection")
def disconnect(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if conn := db.get(MailConnection, user.id):
        db.delete(conn)
        audit(db, user, "mail_connection", user.id, "disconnect", {"account": conn.account})
        db.commit()
    mail.forget_user_token(user.id)
    return _connection_out(None, user)


# ---------------------------------------------------------------- sender (administrators)
def _sender_out(db: Session) -> dict:
    s = get_settings()
    cur = mail.sender_settings()
    service = db.get(MailConnection, cur["service_user_id"]) if cur["service_user_id"] else None
    return {
        "from": cur["from"] or None, "from_name": cur["from_name"] or None,
        "default_from": s.mail_from or None, "default_from_name": s.mail_from_name or None,
        "backend": mail.backend_for(), "delegated": mail.status()["delegated"],
        "service_user": {"id": service.user_id, "name": service.user.full_name, "account": service.account,
                         "last_error": service.last_error} if service else None,
        "connections": [{"user": c.user.full_name, "email": c.user.email, "account": c.account,
                         "connected_at": c.connected_at, "last_used_at": c.last_used_at, "last_error": c.last_error}
                        for c in db.scalars(select(MailConnection).order_by(MailConnection.connected_at.desc()))],
    }


@router.get("/sender")
def get_sender(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _sender_out(db)


class SenderIn(BaseModel):
    from_address: EmailStr | None = None  # empty = CRM_MAIL_FROM
    from_name: str | None = Field(default=None, max_length=120)
    use_my_connection_for_automatic: bool | None = None  # True: my Microsoft 365 connection sends automatic email


@router.put("/sender")
def set_sender(data: SenderIn, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Who email is sent as (quotes, emails, notices, campaigns), whatever the user who sends it."""
    row = db.get(AppSetting, mail.SENDER_KEY) or AppSetting(key=mail.SENDER_KEY, value={})
    value = dict(row.value or {})
    value["from"] = str(data.from_address).lower() if data.from_address else None
    value["from_name"] = (data.from_name or "").strip() or None
    if data.use_my_connection_for_automatic is not None:
        if data.use_my_connection_for_automatic:
            if not db.get(MailConnection, user.id):
                raise HTTPException(422, "Connect your Microsoft 365 account first")
            value["service_user_id"] = user.id
        elif value.get("service_user_id") == user.id:
            value["service_user_id"] = None
    row.value, row.updated_by_id = value, user.id
    db.add(row)
    audit(db, user, "app_setting", 0, "update", {"key": mail.SENDER_KEY, **value})
    db.commit()
    mail.forget_sender_settings()
    return _sender_out(db)

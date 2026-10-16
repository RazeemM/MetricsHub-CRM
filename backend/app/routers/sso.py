"""Single sign-on with OpenID Connect (authorization code flow + PKCE).

Flow: browser -> /api/auth/sso/login -> identity provider -> /api/auth/sso/callback
      -> CRM issues its own access token -> redirect to {app_url}/sso#token=...
"""
import base64
import datetime as dt
import hashlib
import logging
import secrets
import time
from functools import lru_cache
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..crud import audit
from ..db import get_db
from ..models import User
from ..security import ALGORITHM, create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
STATE_COOKIE = "crm_sso_state"
log = logging.getLogger("crm.sso")


@lru_cache(maxsize=4)
def _discovery(issuer: str) -> dict:
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


class SsoSetupError(Exception):
    pass


def _metadata(issuer: str) -> dict:
    """The provider's OpenID configuration, or SsoSetupError with a message an administrator can act on."""
    try:
        return _discovery(issuer)
    except httpx.HTTPStatusError as exc:
        log.error("SSO discovery %s returned HTTP %s", exc.request.url, exc.response.status_code)
        raise SsoSetupError(f"The identity provider answered HTTP {exc.response.status_code} for "
                            f"CRM_OIDC_ISSUER ({issuer}). Check the tenant ID and the /v2.0 ending.") from None
    except httpx.HTTPError as exc:
        log.error("SSO discovery for %s failed: %r", issuer, exc)
        host = httpx.URL(issuer).host if issuer.startswith("http") else issuer
        raise SsoSetupError(f"The CRM server cannot reach {host} ({type(exc).__name__}). Allow outbound HTTPS from "
                            "the server to it, or set HTTPS_PROXY for the API container.") from None
    except ValueError:
        raise SsoSetupError(f"CRM_OIDC_ISSUER ({issuer}) did not return an OpenID configuration") from None


def _provider_error(exc: httpx.HTTPStatusError) -> str:
    """Microsoft explains a refused code exchange (bad secret, wrong redirect URI...) in error_description."""
    try:
        body = exc.response.json()
        desc = (body.get("error_description") or body.get("error") or "").split("\r\n")[0].split("\n")[0]
    except ValueError:
        desc = ""
    log.error("SSO token exchange refused (HTTP %s): %s", exc.response.status_code, desc)
    return f"The identity provider refused the sign-in: {desc[:300]}" if desc else \
        f"The identity provider refused the sign-in (HTTP {exc.response.status_code})"


@lru_cache(maxsize=4)
def _jwks_client(jwks_uri: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_uri, cache_keys=True)


def _callback_url(_: Request) -> str:
    # Register exactly this URL as the redirect URI in your identity provider
    return f"{get_settings().app_url.rstrip('/')}/api/auth/sso/callback"


def _fail(reason: str) -> RedirectResponse:
    resp = RedirectResponse(f"{get_settings().app_url}/login?{urlencode({'sso_error': reason})}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    return resp


@router.get("/config")
def auth_config():
    s = get_settings()
    return {"sso_enabled": s.sso_enabled, "sso_label": s.oidc_button_label,
            "password_login_enabled": s.password_login_enabled or not s.sso_enabled}


@router.get("/sso/login")
def sso_login(request: Request):
    s = get_settings()
    if not s.sso_enabled:
        return _fail("SSO is not configured")
    try:
        meta = _metadata(s.oidc_issuer)
    except SsoSetupError as exc:
        return _fail(str(exc))
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    params = {
        "client_id": s.oidc_client_id, "response_type": "code", "scope": s.oidc_scopes,
        "redirect_uri": _callback_url(request), "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
    }
    cookie = jwt.encode({"state": state, "nonce": nonce, "verifier": verifier, "exp": int(time.time()) + 600},
                        s.secret_key, algorithm=ALGORITHM)
    resp = RedirectResponse(f"{meta['authorization_endpoint']}?{urlencode(params)}", status_code=302)
    resp.set_cookie(STATE_COOKIE, cookie, max_age=600, httponly=True, samesite="lax", path="/api/auth",
                    secure=request.url.scheme == "https")
    return resp


@router.get("/sso/callback", name="sso_callback")
def sso_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                 error_description: str | None = None, db: Session = Depends(get_db)):
    s = get_settings()
    if error:
        return _fail(error_description or error)
    try:
        saved = jwt.decode(request.cookies.get(STATE_COOKIE, ""), s.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return _fail("Sign-in session expired, please try again")
    if not code or not state or not secrets.compare_digest(state, saved["state"]):
        return _fail("Invalid sign-in state")

    try:
        meta = _metadata(s.oidc_issuer)
    except SsoSetupError as exc:
        return _fail(str(exc))
    try:
        token_res = httpx.post(meta["token_endpoint"], timeout=15, data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _callback_url(request),
            "client_id": s.oidc_client_id, "client_secret": s.oidc_client_secret,
            "code_verifier": saved["verifier"]})
        token_res.raise_for_status()
        id_token = token_res.json()["id_token"]
        key = _jwks_client(meta["jwks_uri"]).get_signing_key_from_jwt(id_token)
        expected_issuer = meta.get("issuer", s.oidc_issuer)
        if "{tenantid}" in expected_issuer:  # Entra multitenant ("organizations") endpoint
            tid = jwt.decode(id_token, options={"verify_signature": False}).get("tid", "")
            expected_issuer = expected_issuer.replace("{tenantid}", tid)
        claims = jwt.decode(id_token, key.key, algorithms=["RS256", "RS384", "RS512", "ES256", "PS256"],
                            audience=s.oidc_client_id, issuer=expected_issuer, leeway=60)
    except httpx.HTTPStatusError as exc:
        return _fail(_provider_error(exc))
    except (httpx.HTTPError, KeyError, jwt.PyJWTError) as exc:
        log.error("SSO sign-in could not be verified: %r", exc)
        return _fail(f"Could not verify sign-in: {type(exc).__name__}")
    if claims.get("nonce") != saved["nonce"]:
        return _fail("Invalid sign-in nonce")

    email = (claims.get("email") or claims.get("preferred_username") or claims.get("upn") or "").strip().lower()
    if "@" not in email:
        return _fail("Your identity provider did not return an email address")
    subject = f"{claims.get('iss')}|{claims.get('sub')}"

    user = db.scalar(select(User).where(User.sso_subject == subject)) or db.scalar(
        select(User).where(func.lower(User.email) == email))
    if not user:
        allowed = {d.strip().lower() for d in s.oidc_auto_provision_domains.split(",") if d.strip()}
        if email.rsplit("@", 1)[1] not in allowed:
            return _fail("No CRM account exists for this email. Ask an administrator to invite you.")
        user = User(email=email, full_name=claims.get("name") or email.split("@")[0],
                    password_hash="!sso-only", role=s.oidc_default_role, is_active=True)
        db.add(user)
        db.flush()
        audit(db, user, "user", user.id, "create", {"via": "sso"})
    if not user.is_active:
        return _fail("Your CRM account is disabled")
    if not user.sso_subject:
        user.sso_subject = subject
    user.last_login_at = dt.datetime.now(dt.UTC)
    db.commit()

    resp = RedirectResponse(f"{s.app_url}/sso#token={create_access_token(user.id)}", status_code=302)
    resp.delete_cookie(STATE_COOKIE, path="/api/auth")
    return resp

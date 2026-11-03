"""Outgoing email: SMTP, Microsoft 365 (Microsoft Graph sendMail) or a log-only backend.

Two purposes can use different backends:
  transactional  one-to-one mail such as quotes (CRM_MAIL_BACKEND)
  bulk           campaigns and newsletters (CRM_BULK_MAIL_BACKEND; empty = same as CRM_MAIL_BACKEND)

Backends:
  disabled  sending is off (default)
  smtp      any SMTP server or relay (Microsoft 365 SMTP AUTH, Brevo, SendGrid, Amazon SES, your own Postfix...)
  graph     Microsoft Graph: the CRM authenticates as the Entra ID app (application permission Mail.Send) and sends
            from the signed-in user's own mailbox, so messages appear in their Outlook Sent Items. Restrict which
            mailboxes the app may send as with an Exchange Online application access policy (see README).
  graph_delegated
            Microsoft Graph with the delegated permission Mail.Send.Shared: each user connects their Microsoft 365
            account once (authorization code + PKCE, offline_access); the CRM keeps the refresh token encrypted and
            sends through /me/sendMail from the shared mailbox (the sender set in the app), which the user needs
            Send As rights on. Automatic emails (campaigns, notices) use the connection an administrator chose.
  log       nothing leaves the server; messages are kept in memory (staging, demos, tests)
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import html as html_lib
import re
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass, field
from email import policy as email_policy
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

import logging

import httpx
from fastapi import HTTPException

from .config import get_settings

log = logging.getLogger("crm.mail")

GRAPH = "https://graph.microsoft.com/v1.0"
MAX_ATTACHMENTS_BYTES = 3_000_000  # Graph limit for attachments sent inline with sendMail


class MailError(Exception):
    pass


def http_error(exc: MailError, what: str = "send") -> HTTPException:
    """A mail server's refusal as an API error. It is logged (docker compose logs api), and returned as 422, not
    5xx: reverse proxies (IIS/ARR, nginx error pages) often replace 5xx bodies, which hides the reason."""
    log.warning("Could not %s email: %s", what, exc)
    return HTTPException(422, f"Could not send the email. {exc}")


@dataclass
class Attachment:
    name: str
    content: bytes
    content_type: str = "application/pdf"


@dataclass
class Message:
    sender: str
    to: list[str]
    subject: str
    html: str
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    reply_to: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    from_name: str | None = None
    text: str | None = None  # plain-text part; derived from the HTML when empty
    headers: dict[str, str] = field(default_factory=dict)  # e.g. List-Unsubscribe (SMTP only)
    user_id: int | None = None  # graph_delegated: whose Microsoft 365 sign-in sends it (None = automatic email)


# messages "sent" with the log backend
outbox: list[Message] = []

_tokens: dict[str, tuple[str, float]] = {}  # tenant -> (access token, expiry)
_lock = threading.Lock()
transport: httpx.BaseTransport | None = None  # tests replace this with a fake Graph
smtp_factory = None  # tests replace this with a fake SMTP connection factory


def _client() -> httpx.Client:
    return httpx.Client(transport=transport, timeout=30)


def backend_for(purpose: str = "transactional") -> str:
    s = get_settings()
    if purpose == "bulk" and s.bulk_mail_backend:
        return s.bulk_mail_backend
    return s.mail_backend


# ---------------------------------------------------------------- sender (administrators set it in the app)
SENDER_KEY = "mail_sender"
_sender_cache: tuple[float, dict] | None = None


def sender_settings() -> dict:
    """The sender address and name saved in the app, else CRM_MAIL_FROM / CRM_MAIL_FROM_NAME, and the user whose
    Microsoft 365 connection sends automatic emails (graph_delegated)."""
    global _sender_cache
    if _sender_cache and _sender_cache[0] > time.time():
        saved = _sender_cache[1]
    else:
        from sqlalchemy.exc import SQLAlchemyError

        from .db import SessionLocal
        from .models import AppSetting
        try:
            with SessionLocal() as db:
                row = db.get(AppSetting, SENDER_KEY)
                saved = row.value if row and isinstance(row.value, dict) else {}
        except SQLAlchemyError:
            saved = {}
        _sender_cache = (time.time() + 30, saved)
    s = get_settings()
    return {"from": saved.get("from") or s.mail_from, "from_name": saved.get("from_name") or s.mail_from_name,
            "service_user_id": saved.get("service_user_id")}


def forget_sender_settings() -> None:
    global _sender_cache
    _sender_cache = None


def mail_from() -> str:
    return sender_settings()["from"]


def tenant_for(sender: str) -> str:
    """CRM_GRAPH_TENANT_ID is one tenant id, or "domain=tenant" pairs when mailboxes live in several tenants
    (e.g. "metricshub.com=<id>,sentrysoftware.com=<id>"). Empty = the tenant in CRM_OIDC_ISSUER."""
    s = get_settings()
    raw = s.graph_tenant_id.strip()
    if "=" in raw:
        pairs = dict(p.strip().split("=", 1) for p in raw.split(",") if "=" in p)
        return pairs.get(sender.rsplit("@", 1)[-1].lower(), "")
    if raw:
        return raw
    if "login.microsoftonline.com/" in s.oidc_issuer:
        tenant = s.oidc_issuer.split("login.microsoftonline.com/")[1].split("/")[0]
        return "" if tenant in ("common", "organizations", "consumers") else tenant
    return ""


def graph_credentials() -> tuple[str, str]:
    """Client id and secret. Defaults to the SSO app registration."""
    s = get_settings()
    return s.graph_client_id or s.oidc_client_id, s.graph_client_secret or s.oidc_client_secret


def _configured(backend: str) -> bool:
    s = get_settings()
    if backend == "log":
        return True
    if backend == "smtp":
        return bool(s.smtp_host and mail_from())
    if backend == "graph":
        return all(graph_credentials()) and bool(s.graph_tenant_id.strip() or tenant_for("x@x"))
    if backend == "graph_delegated":
        return all(graph_credentials()) and bool(mail_from()) and bool(tenant_for(mail_from()))
    return False


def status(purpose: str = "transactional") -> dict:
    backend = backend_for(purpose)
    return {"enabled": backend != "disabled" and _configured(backend), "backend": backend,
            "fixed_sender": mail_from() or None, "delegated": backend == "graph_delegated"}


def sender_for(user_email: str, purpose: str = "transactional") -> str:
    """The sender set in the app (or CRM_MAIL_FROM), which SMTP and graph_delegated always use; without one, Graph
    (application permission) sends from the user's own mailbox."""
    if backend_for(purpose) in ("smtp", "graph_delegated"):
        return mail_from()
    return mail_from() or user_email


def needs_connection(user_id: int) -> bool:
    """graph_delegated: the user has not connected Microsoft 365 yet, so cannot send."""
    if backend_for() != "graph_delegated":
        return False
    from .db import SessionLocal
    from .models import MailConnection
    with SessionLocal() as db:
        return db.get(MailConnection, user_id) is None


def html_to_text(html: str) -> str:
    """A readable plain-text part for an HTML email."""
    t = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", "", html)
    t = re.sub(r'(?is)<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', lambda m: f"{m.group(2)} ({m.group(1)})", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</(p|div|h[1-6]|tr|li|table)>", "\n", t)
    t = re.sub(r"(?i)<li[^>]*>", "- ", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = html_lib.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", t).strip()


# ---------------------------------------------------------------- SMTP
def _smtp_connect():
    s = get_settings()
    if smtp_factory:
        return smtp_factory()
    try:
        context = ssl.create_default_context()
        if s.smtp_security == "ssl":
            conn = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=30, context=context)
        else:
            conn = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30)
            conn.ehlo()
            if s.smtp_security == "starttls":
                conn.starttls(context=context)
                conn.ehlo()
        if s.smtp_username:
            conn.login(s.smtp_username, s.smtp_password)
        return conn
    except smtplib.SMTPAuthenticationError as exc:
        raise MailError(f"The SMTP server refused the login ({exc.smtp_code})") from None
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"Could not connect to the SMTP server {s.smtp_host}:{s.smtp_port}: {exc}") from None


# RFC 5322 allows 998-character header lines: with the default 78, long URLs in List-Unsubscribe get MIME-encoded
# and mail clients no longer recognise them
MIME_POLICY = email_policy.SMTP.clone(max_line_length=998)


def build_mime(msg: Message) -> EmailMessage:
    m = EmailMessage(policy=MIME_POLICY)
    m["From"] = formataddr((msg.from_name or sender_settings()["from_name"] or "", msg.sender))
    m["To"] = ", ".join(msg.to)
    if msg.cc:
        m["Cc"] = ", ".join(msg.cc)
    if msg.reply_to:
        m["Reply-To"] = msg.reply_to
    m["Subject"] = msg.subject
    m["Date"] = formatdate(localtime=False)
    m["Message-ID"] = make_msgid(domain=msg.sender.rsplit("@", 1)[-1])
    for k, v in msg.headers.items():
        m[k] = v
    m.set_content(msg.text or html_to_text(msg.html))
    m.add_alternative(msg.html, subtype="html")
    for a in msg.attachments:
        maintype, _, subtype = a.content_type.partition("/")
        m.add_attachment(a.content, maintype=maintype, subtype=subtype or "octet-stream", filename=a.name)
    return m


def _smtp_send(conn, msg: Message) -> None:
    try:
        conn.send_message(build_mime(msg), from_addr=get_settings().smtp_envelope_from or msg.sender,
                          to_addrs=[*msg.to, *msg.cc, *msg.bcc])
    except smtplib.SMTPRecipientsRefused as exc:
        raise MailError(f"Recipient refused by the SMTP server: {', '.join(exc.recipients)}") from None
    except smtplib.SMTPResponseException as exc:
        raise MailError(f"SMTP error {exc.smtp_code}: {exc.smtp_error.decode(errors='replace')[:200]}") from None
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"SMTP error: {exc}") from None


# ---------------------------------------------------------------- Graph
def _access_token(tenant: str) -> str:
    with _lock:
        cached = _tokens.get(tenant)
        if cached and cached[1] > time.time() + 60:
            return cached[0]
        client_id, secret = graph_credentials()
        with _client() as c:
            r = c.post(f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data={
                "grant_type": "client_credentials", "client_id": client_id, "client_secret": secret,
                "scope": "https://graph.microsoft.com/.default"})
        if r.status_code != 200:
            raise MailError(f"Microsoft sign-in failed: {_error(r)}")
        body = r.json()
        _tokens[tenant] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return body["access_token"]


def _error(r: httpx.Response) -> str:
    try:
        body = r.json()
        err = body.get("error")
        if isinstance(err, dict):
            return f"{err.get('code')}: {err.get('message')}"
        return f"{err}: {body.get('error_description', '')}".strip(": ")
    except ValueError:
        return f"HTTP {r.status_code}"


def _recipients(addresses: list[str]) -> list[dict]:
    return [{"emailAddress": {"address": a}} for a in addresses]


# ---------------------------------------------------------------- Graph, delegated (each user signs in)
_user_tokens: dict[int, tuple[str, float]] = {}  # user id -> (access token, expiry)


def _fernet():
    from cryptography.fernet import Fernet
    key = hashlib.sha256(("mail-connection:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def seal(token: str) -> str:
    """Encrypt a refresh token for the database."""
    return _fernet().encrypt(token.encode()).decode()


def unseal(sealed: str) -> str:
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(sealed.encode()).decode()
    except InvalidToken:
        raise MailError("The saved Microsoft 365 sign-in can no longer be read (CRM_SECRET_KEY changed): "
                        "connect Microsoft 365 again") from None


def token_endpoint(tenant: str) -> str:
    return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"


def sending_user(msg: Message) -> int | None:
    """Whose Microsoft 365 sign-in sends a message: the user who sends it, else (automatic email) the connection an
    administrator chose. A user without a connection of their own never borrows another's: Exchange's Send As rights
    decide who may send as the shared mailbox."""
    return msg.user_id if msg.user_id is not None else sender_settings()["service_user_id"]


def _delegated_token(user_id: int | None, tenant: str, automatic: bool) -> tuple[str, str]:
    """An access token from the user's saved sign-in (refreshed when needed), and the account it belongs to."""
    from .db import SessionLocal
    from .models import MailConnection

    if user_id is None:
        raise MailError("Automatic emails have no Microsoft 365 connection: an administrator chooses one in "
                        "System status > Email")
    with _lock, SessionLocal() as db:
        conn = db.get(MailConnection, user_id)
        if not conn:
            raise MailError("The Microsoft 365 connection for automatic emails was removed: an administrator chooses "
                            "one in System status > Email" if automatic else
                            "Connect your Microsoft 365 account first (Connect Microsoft 365 in the email dialog)")
        now = dt.datetime.now(dt.UTC)
        cached = _user_tokens.get(user_id)
        if cached and cached[1] > time.time() + 60:
            conn.last_used_at = now
            db.commit()
            return cached[0], conn.account
        client_id, secret = graph_credentials()
        with _client() as c:
            r = c.post(token_endpoint(tenant), data={
                "grant_type": "refresh_token", "client_id": client_id, "client_secret": secret,
                "refresh_token": unseal(conn.refresh_token), "scope": get_settings().graph_delegated_scopes})
        if r.status_code != 200:
            conn.last_error = f"{now:%d %b %Y %H:%M} UTC: {_error(r)}"[:1000]
            db.commit()
            raise MailError(f"The Microsoft 365 sign-in of {conn.account} is no longer valid ({_error(r)}): "
                            "connect Microsoft 365 again")
        body = r.json()
        if body.get("refresh_token"):  # Microsoft rotates refresh tokens
            conn.refresh_token = seal(body["refresh_token"])
        conn.last_error, conn.last_used_at = None, now
        db.commit()
        _user_tokens[user_id] = (body["access_token"], time.time() + int(body.get("expires_in", 3600)))
        return body["access_token"], conn.account


def forget_user_token(user_id: int) -> None:
    _user_tokens.pop(user_id, None)


def _graph_send(msg: Message, delegated: bool = False) -> None:
    if sum(len(a.content) for a in msg.attachments) > MAX_ATTACHMENTS_BYTES:
        raise MailError("Attachments are too large to send (max 3 MB)")
    payload = {
        "message": {
            "subject": msg.subject,
            "body": {"contentType": "HTML", "content": msg.html},
            "toRecipients": _recipients(msg.to),
            "ccRecipients": _recipients(msg.cc),
            "bccRecipients": _recipients(msg.bcc),
            "replyTo": _recipients([msg.reply_to]) if msg.reply_to else [],
            "attachments": [{
                "@odata.type": "#microsoft.graph.fileAttachment", "name": a.name, "contentType": a.content_type,
                "contentBytes": base64.b64encode(a.content).decode()} for a in msg.attachments],
        },
        "saveToSentItems": True,
    }
    tenant = tenant_for(msg.sender)
    if not tenant:
        raise MailError(f"No Microsoft 365 tenant configured for {msg.sender} (CRM_GRAPH_TENANT_ID)")
    if delegated:
        # /me/sendMail with "from": Send As on the shared mailbox is enough (/users/{mailbox} would need Full Access)
        uid = sending_user(msg)
        token, account = _delegated_token(uid, tenant, automatic=msg.user_id is None)
        if msg.sender.lower() != account.lower():
            payload["message"]["from"] = {"emailAddress": {"address": msg.sender,
                                                           "name": msg.from_name or sender_settings()["from_name"]}}
        url = f"{GRAPH}/me/sendMail"
    else:
        token = _access_token(tenant)
        url = f"{GRAPH}/users/{msg.sender}/sendMail"
    with _client() as c:
        r = c.post(url, json=payload, headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 401:
        if delegated:
            forget_user_token(uid)
        else:
            _tokens.pop(tenant, None)
    if r.status_code != 202:
        hint = ""
        if delegated and r.status_code in (403, 404):
            hint = (f" Check that {account} has Send As on {msg.sender} in Exchange, and that the app has the "
                    "delegated Mail.Send.Shared permission.")
        elif r.status_code in (403, 404):
            hint = (f" Check that the app has the Mail.Send application permission with admin consent and may send "
                    f"as {msg.sender}.")
        raise MailError(f"Microsoft 365 refused the message: {_error(r)}.{hint}")


# ---------------------------------------------------------------- sending
class MailSession:
    """Sends several messages over one connection (SMTP); use for bulk sending."""

    def __init__(self, purpose: str = "transactional"):
        self.purpose = purpose
        self.backend = backend_for(purpose)
        self.conn = None

    def __enter__(self) -> MailSession:
        from . import monitoring
        try:
            if not status(self.purpose)["enabled"]:
                raise MailError("Email sending is not configured (CRM_MAIL_BACKEND)")
            if self.backend == "smtp":
                self.conn = _smtp_connect()
        except MailError as exc:
            monitoring.record_mail(self.purpose, False, error=str(exc))
            raise
        return self

    def send(self, msg: Message) -> None:
        from . import monitoring
        try:
            if self.backend == "log":
                outbox.append(msg)
            elif self.backend == "smtp":
                _smtp_send(self.conn, msg)
            elif self.backend == "graph":
                _graph_send(msg)
            elif self.backend == "graph_delegated":
                _graph_send(msg, delegated=True)
            else:
                raise MailError("Email sending is not configured")
        except MailError as exc:
            monitoring.record_mail(self.purpose, False, msg, str(exc))
            raise
        monitoring.record_mail(self.purpose, True)

    def __exit__(self, *exc) -> None:
        if self.conn is not None:
            try:
                self.conn.quit()
            except (smtplib.SMTPException, OSError):
                pass


def send(msg: Message, purpose: str = "transactional") -> None:
    with MailSession(purpose) as session:
        session.send(msg)

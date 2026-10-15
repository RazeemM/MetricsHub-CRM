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
  log       nothing leaves the server; messages are kept in memory (staging, demos, tests)
"""
from __future__ import annotations

import base64
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

import httpx

from .config import get_settings

GRAPH = "https://graph.microsoft.com/v1.0"
MAX_ATTACHMENTS_BYTES = 3_000_000  # Graph limit for attachments sent inline with sendMail


class MailError(Exception):
    pass


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
        return bool(s.smtp_host and s.mail_from)
    if backend == "graph":
        return all(graph_credentials()) and bool(s.graph_tenant_id.strip() or tenant_for("x@x"))
    return False


def status(purpose: str = "transactional") -> dict:
    s = get_settings()
    backend = backend_for(purpose)
    fixed = s.mail_from if backend == "smtp" else (s.mail_from or None)
    return {"enabled": backend != "disabled" and _configured(backend), "backend": backend,
            "fixed_sender": fixed or None}


def sender_for(user_email: str, purpose: str = "transactional") -> str:
    """SMTP always sends from CRM_MAIL_FROM (relays only accept verified senders); Graph sends from the user."""
    s = get_settings()
    if backend_for(purpose) == "smtp":
        return s.mail_from
    return s.mail_from or user_email


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
    m["From"] = formataddr((msg.from_name or get_settings().mail_from_name or "", msg.sender))
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


def _graph_send(msg: Message) -> None:
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
    token = _access_token(tenant)
    with _client() as c:
        r = c.post(f"{GRAPH}/users/{msg.sender}/sendMail", json=payload,
                   headers={"Authorization": f"Bearer {token}"})
    if r.status_code == 401:
        _tokens.pop(tenant, None)
    if r.status_code != 202:
        hint = ""
        if r.status_code in (403, 404):
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
        if not status(self.purpose)["enabled"]:
            raise MailError("Email sending is not configured (CRM_MAIL_BACKEND)")
        if self.backend == "smtp":
            self.conn = _smtp_connect()
        return self

    def send(self, msg: Message) -> None:
        if self.backend == "log":
            outbox.append(msg)
        elif self.backend == "smtp":
            _smtp_send(self.conn, msg)
        elif self.backend == "graph":
            _graph_send(msg)
        else:
            raise MailError("Email sending is not configured")

    def __exit__(self, *exc) -> None:
        if self.conn is not None:
            try:
                self.conn.quit()
            except (smtplib.SMTPException, OSError):
                pass


def send(msg: Message, purpose: str = "transactional") -> None:
    with MailSession(purpose) as session:
        session.send(msg)

"""Outgoing email through Microsoft 365 (Microsoft Graph sendMail).

The CRM authenticates as the Entra ID app (client credentials, application permission Mail.Send) and sends from
the signed-in user's own mailbox, so messages appear in their Outlook Sent Items. Restrict which mailboxes the app
may send as with an Exchange Online application access policy (see README).

CRM_MAIL_BACKEND:
  disabled  sending is off (default)
  graph     Microsoft Graph
  log       nothing leaves the server; messages are kept in memory (staging, demos, tests)
"""
from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass, field

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


# messages "sent" with the log backend
outbox: list[Message] = []

_tokens: dict[str, tuple[str, float]] = {}  # tenant -> (access token, expiry)
_lock = threading.Lock()
transport: httpx.BaseTransport | None = None  # tests replace this with a fake Graph


def _client() -> httpx.Client:
    return httpx.Client(transport=transport, timeout=30)


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


def status() -> dict:
    s = get_settings()
    backend = s.mail_backend
    configured = backend == "log" or (backend == "graph" and all(graph_credentials())
                                       and bool(s.graph_tenant_id.strip() or tenant_for("x@x")))
    return {"enabled": backend != "disabled" and configured, "backend": backend,
            "fixed_sender": s.mail_from or None}


def sender_for(user_email: str) -> str:
    return get_settings().mail_from or user_email


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


def send(msg: Message) -> None:
    s = get_settings()
    if not status()["enabled"]:
        raise MailError("Email sending is not configured (CRM_MAIL_BACKEND)")
    if sum(len(a.content) for a in msg.attachments) > MAX_ATTACHMENTS_BYTES:
        raise MailError("Attachments are too large to send (max 3 MB)")
    if s.mail_backend == "log":
        outbox.append(msg)
        return
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

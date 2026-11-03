"""Sending as a shared mailbox with Microsoft Graph delegated permissions (fake Microsoft, no network)."""
import json
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest

from app import mail
from app.config import get_settings
from app.db import SessionLocal
from app.models import MailConnection

SENDER = "crm@sentry.example"


@pytest.fixture
def ms(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "mail_backend", "graph_delegated")
    monkeypatch.setattr(s, "oidc_issuer", "https://login.microsoftonline.com/tenant-123/v2.0")
    monkeypatch.setattr(s, "oidc_client_id", "crm-app")
    monkeypatch.setattr(s, "oidc_client_secret", "s3cret")
    monkeypatch.setattr(s, "mail_from", "")
    mail._user_tokens.clear()
    mail.forget_sender_settings()
    state = {"sent": [], "grants": [], "refresh_status": 200, "refresh": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            assert request.url.path == "/tenant-123/oauth2/v2.0/token" and form["client_secret"] == "s3cret"
            assert "Mail.Send.Shared" in form["scope"] and "offline_access" in form["scope"]
            state["grants"].append(form)
            if form["grant_type"] == "authorization_code":
                assert form["code"] == "the-code" and len(form["code_verifier"]) > 40
                id_token = jwt.encode({"preferred_username": "Admin@Example.com"}, "x", algorithm="HS256")
                return httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600,
                                                 "id_token": id_token, "scope": form["scope"]})
            if state["refresh_status"] != 200:
                return httpx.Response(400, json={"error": "invalid_grant",
                                                 "error_description": "AADSTS700082: The refresh token has expired"})
            state["refresh"] += 1
            return httpx.Response(200, json={"access_token": f"at-r{state['refresh']}",
                                             "refresh_token": f"rt-r{state['refresh']}", "expires_in": 3600})
        state["sent"].append({"path": request.url.path, "auth": request.headers["Authorization"],
                              **json.loads(request.content)})
        return httpx.Response(202)

    monkeypatch.setattr(mail, "transport", httpx.MockTransport(handler))
    yield state
    mail.forget_sender_settings()


def _connect(client) -> httpx.Response:
    r = client.post("/api/mail/microsoft/connect", json={"return_to": "/opportunities/1"})
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["url"])
    q = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert url.netloc == "login.microsoftonline.com" and url.path == "/tenant-123/oauth2/v2.0/authorize"
    assert q["code_challenge_method"] == "S256" and q["redirect_uri"].endswith("/api/mail/microsoft/callback")
    return client.get("/api/mail/microsoft/callback", params={"code": "the-code", "state": q["state"]},
                      follow_redirects=False)


def test_sender_is_set_in_the_app_and_each_user_connects(client, ms):
    r = client.put("/api/mail/sender", json={"from_address": SENDER, "from_name": "Sentry Software CRM"})
    assert r.status_code == 200 and r.json()["from"] == SENDER
    info = client.get("/api/email/compose").json()
    assert info["sender"] == SENDER and info["connect_required"] is True  # signed in as admin@example.com
    assert info["reply_to"] == "admin@example.com"
    body = {"to": "buyer@example.org", "subject": "Quote", "body": "Hello"}
    r = client.post("/api/email/send", data=body)
    assert r.status_code == 422 and "Connect your Microsoft 365 account" in r.json()["detail"]

    r = _connect(client)
    assert r.status_code == 302 and r.headers["location"].endswith("/opportunities/1?microsoft365=connected")
    with SessionLocal() as db:
        conn = db.get(MailConnection, 1)
        assert conn.account == "admin@example.com" and "rt-1" not in conn.refresh_token  # kept encrypted
        assert mail.unseal(conn.refresh_token) == "rt-1"
    me = client.get("/api/mail/microsoft/connection").json()
    assert me["connected"] and me["required"] and me["sender"] == SENDER
    assert client.get("/api/email/compose").json()["connect_required"] is False

    r = client.post("/api/email/send", data=body)
    assert r.status_code == 200, r.text
    sent = ms["sent"][-1]
    assert sent["path"] == "/v1.0/me/sendMail" and sent["auth"] == "Bearer at-r1"
    assert sent["message"]["from"]["emailAddress"] == {"address": SENDER, "name": "Administrator"}  # the user's name
    assert sent["message"]["replyTo"][0]["emailAddress"]["address"] == "admin@example.com"
    assert ms["grants"][-1]["refresh_token"] == "rt-1"
    with SessionLocal() as db:  # Microsoft rotated the refresh token
        assert mail.unseal(db.get(MailConnection, 1).refresh_token) == "rt-r1"


def test_automatic_email_uses_the_connection_an_admin_chose(client, ms):
    client.delete("/api/mail/microsoft/connection")
    client.put("/api/mail/sender", json={"from_address": SENDER, "use_my_connection_for_automatic": False})
    notice = mail.Message(sender=mail.mail_from(), to=["owner@example.org"], subject="Renewal due", html="<p>x</p>")
    with pytest.raises(mail.MailError, match="no Microsoft 365 connection"):
        mail.send(notice)
    r = client.put("/api/mail/sender", json={"from_address": SENDER, "use_my_connection_for_automatic": True})
    assert r.status_code == 422  # not connected yet
    _connect(client)
    r = client.put("/api/mail/sender", json={"from_address": SENDER, "use_my_connection_for_automatic": True})
    assert r.json()["service_user"]["account"] == "admin@example.com"
    mail.send(notice)
    assert ms["sent"][-1]["message"]["from"]["emailAddress"]["address"] == SENDER


def test_expired_sign_in_asks_to_reconnect(client, ms):
    client.put("/api/mail/sender", json={"from_address": SENDER})
    _connect(client)
    ms["refresh_status"] = 400
    with pytest.raises(mail.MailError, match="connect Microsoft 365 again"):
        mail.send(mail.Message(sender=SENDER, to=["x@example.org"], subject="s", html="h", user_id=1))
    assert "AADSTS700082" in client.get("/api/mail/microsoft/connection").json()["last_error"]
    assert client.delete("/api/mail/microsoft/connection").json()["connected"] is False


def test_callback_refuses_a_forged_state(client, ms):
    client.post("/api/mail/microsoft/connect", json={})
    r = client.get("/api/mail/microsoft/callback", params={"code": "the-code", "state": "forged"},
                   follow_redirects=False)
    assert "microsoft365_error=Invalid" in r.headers["location"]
    assert client.get("/api/mail/microsoft/connection").json()["connected"] is False


def test_sender_defaults_to_crm_mail_from(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_from", "default@sentry.example")
    mail.forget_sender_settings()
    client.put("/api/mail/sender", json={"from_address": None})
    assert mail.mail_from() == "default@sentry.example"
    client.put("/api/mail/sender", json={"from_address": "Other@Sentry.example"})
    assert mail.mail_from() == "other@sentry.example"
    client.put("/api/mail/sender", json={"from_address": None})

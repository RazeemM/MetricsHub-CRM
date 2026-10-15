"""Emailing quotes through Microsoft Graph (fake Graph server, no network)."""
import base64
import json

import httpx
import pytest

from app import mail
from app.config import get_settings
from app.routers import quotes as quotes_router

FAKE_PDF = b"%PDF-1.7 fake quote"


@pytest.fixture
def graph(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "mail_backend", "graph")
    monkeypatch.setattr(s, "oidc_issuer", "https://login.microsoftonline.com/tenant-123/v2.0")
    monkeypatch.setattr(s, "oidc_client_id", "crm-app")
    monkeypatch.setattr(s, "oidc_client_secret", "s3cret")
    monkeypatch.setattr(quotes_router, "render_pdf", lambda html: FAKE_PDF)  # WeasyPrint is not needed here
    mail._tokens.clear()
    state = {"sent": [], "token_calls": 0, "status": 202, "tenants": []}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "login.microsoftonline.com":
            state["tenants"].append(request.url.path.split("/")[1])
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            assert form["grant_type"] == "client_credentials" and form["client_id"] == "crm-app"
            state["token_calls"] += 1
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 3600})
        assert request.headers["Authorization"] == "Bearer tok"
        if state["status"] != 202:
            return httpx.Response(state["status"], json={"error": {"code": "ErrorAccessDenied",
                                                                   "message": "Access is denied."}})
        state["sent"].append({"path": request.url.path, **json.loads(request.content)})
        return httpx.Response(202)

    monkeypatch.setattr(mail, "transport", httpx.MockTransport(handler))
    return state


def _quote(client, ref, qty):
    acc = client.post("/api/accounts", json={"name": f"Mail Co {qty}"}).json()
    c = client.post("/api/contacts", json={"first_name": "Mia", "last_name": "Buyer", "email": f"mia{qty}@mailco.example",
                                           "account_id": acc["id"]}).json()
    opp = client.post("/api/opportunities", json={
        "title": "Mail test", "account_id": acc["id"], "brand_id": ref["brands"]["METRICSHUB"], "primary_contact_id": c["id"],
        "line_items": [{"product_id": ref["products"]["MH-ENT-HOST"]["id"], "quantity": qty}]}).json()
    return opp, client.post(f"/api/opportunities/{opp['id']}/quotes", json={}).json()


def test_draft_and_send_through_graph(client, ref, graph):
    opp, q = _quote(client, ref, 31)
    assert client.get("/api/mail/status").json()["enabled"] is True

    draft = client.get(f"/api/quotes/{q['id']}/email").json()
    assert draft["enabled"] and draft["sender"] == "admin@example.com"
    assert draft["to"] == ["mia31@mailco.example"]
    assert q["number"] in draft["subject"] and "Mail Co 31" in draft["subject"]
    assert draft["body"].startswith("Dear Mia Buyer,") and "{" not in draft["body"]

    r = client.post(f"/api/quotes/{q['id']}/email", json={
        "to": ["mia31@mailco.example"], "cc": ["boss@mailco.example"], "subject": draft["subject"],
        "body": "Hello <script>x</script>\n\n**Thanks**"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "sent"

    sent = graph["sent"][0]
    assert sent["path"] == "/v1.0/users/admin@example.com/sendMail" and sent["saveToSentItems"] is True
    m = sent["message"]
    assert [x["emailAddress"]["address"] for x in m["toRecipients"]] == ["mia31@mailco.example"]
    assert [x["emailAddress"]["address"] for x in m["ccRecipients"]] == ["boss@mailco.example"]
    assert "<script>" not in m["body"]["content"] and "<strong>Thanks</strong>" in m["body"]["content"]
    att = m["attachments"][0]
    assert att["name"] == f"{q['number']}.pdf" and base64.b64decode(att["contentBytes"]) == FAKE_PDF

    acts = client.get("/api/activities", params={"opportunity_id": opp["id"]}).json()["items"]
    assert acts[0]["type"] == "email" and "mia31@mailco.example" in acts[0]["body"]

    # second send reuses the cached token and leaves the status alone
    client.patch(f"/api/quotes/{q['id']}", json={"status": "accepted"})
    r = client.post(f"/api/quotes/{q['id']}/email", json={"to": ["mia31@mailco.example"], "subject": "Again", "body": "x"})
    assert r.json()["status"] == "accepted" and graph["token_calls"] == 1 and graph["tenants"] == ["tenant-123"]


def test_tenant_per_mail_domain(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "oidc_issuer", "https://login.microsoftonline.com/organizations/v2.0")
    monkeypatch.setattr(s, "graph_tenant_id", "")
    assert mail.tenant_for("a@metricshub.com") == ""  # multitenant issuer: tenant must be configured
    monkeypatch.setattr(s, "graph_tenant_id", "metricshub.com=t-mh, sentrysoftware.com=t-sen")
    assert mail.tenant_for("a@metricshub.com") == "t-mh" and mail.tenant_for("b@SentrySoftware.com".lower()) == "t-sen"
    assert mail.tenant_for("c@other.example") == ""


def test_graph_refusal_is_reported_and_nothing_changes(client, ref, graph):
    opp, q = _quote(client, ref, 32)
    graph["status"] = 403
    r = client.post(f"/api/quotes/{q['id']}/email", json={"to": ["mia32@mailco.example"], "subject": "S", "body": "B"})
    assert r.status_code == 502 and "Mail.Send" in r.json()["detail"]
    assert client.get(f"/api/opportunities/{opp['id']}/quotes").json()[0]["status"] == "draft"
    assert client.get("/api/activities", params={"opportunity_id": opp["id"]}).json()["total"] == 0


def test_validation_and_disabled_backend(client, ref, graph, monkeypatch):
    _, q = _quote(client, ref, 33)
    assert client.post(f"/api/quotes/{q['id']}/email", json={"to": [], "subject": "S", "body": "B"}).status_code == 422
    assert client.post(f"/api/quotes/{q['id']}/email",
                       json={"to": ["not-an-email"], "subject": "S", "body": "B"}).status_code == 422
    monkeypatch.setattr(get_settings(), "mail_backend", "disabled")
    assert client.get(f"/api/quotes/{q['id']}/email").json()["enabled"] is False
    r = client.post(f"/api/quotes/{q['id']}/email", json={"to": ["a@b.example"], "subject": "S", "body": "B"})
    assert r.status_code == 503 and graph["sent"] == []


def test_template_email_wording_is_editable(client):
    tpl = client.get("/api/quote-templates").json()[0]
    assert "{quote_number}" in tpl["email_subject"]
    body = {k: v for k, v in tpl.items() if k not in ("brand_id", "brand_name")}
    body["email_subject"] = "Your quote {quote_number}"
    r = client.put(f"/api/quote-templates/{tpl['brand_id']}", json=body)
    assert r.status_code == 200 and r.json()["email_subject"] == "Your quote {quote_number}"

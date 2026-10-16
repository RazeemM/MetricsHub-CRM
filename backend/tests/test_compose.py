"""One-to-one email from the CRM: compose info, sending with attachments, timeline logging."""
from tests.test_email_marketing import smtp  # noqa: F401 - fake SMTP fixture


def test_compose_and_send_from_a_contact(client, smtp):
    acc = client.post("/api/accounts", json={"name": "Compose Co"}).json()
    ct = client.post("/api/contacts", json={"first_name": "Cleo", "email": "cleo@compose.example",
                                            "account_id": acc["id"]}).json()
    info = client.get("/api/email/compose", params={"contact_id": ct["id"]}).json()
    assert info["enabled"] and info["sender"] == "news@metricshub.example" and info["to"] == ["cleo@compose.example"]
    assert info["reply_to"] == "admin@example.com"  # SMTP sends from CRM_MAIL_FROM; replies go to the user

    r = client.post("/api/email/send", data={
        "to": "cleo@compose.example", "cc": "boss@compose.example; Boss@Compose.example", "subject": "Our call",
        "body": "Hi Cleo,\n\n- point one\n- **point two**", "contact_id": str(ct["id"])},
        files=[("files", ("notes.txt", b"hello", "text/plain"))])
    assert r.status_code == 200, r.text
    msg = smtp.sent[-1][0]
    assert msg["To"] == "cleo@compose.example" and msg["Cc"] == "boss@compose.example"
    assert msg["From"] == "Administrator <news@metricshub.example>" and msg["Reply-To"] == "admin@example.com"
    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "<strong>point two</strong>" in html and "<li>point one</li>" in html
    assert next(msg.iter_attachments()).get_filename() == "notes.txt"

    acts = client.get("/api/activities", params={"contact_id": ct["id"]}).json()["items"]
    assert acts[0]["type"] == "email" and acts[0]["subject"] == "Our call" and "notes.txt" in acts[0]["body"]
    assert client.get("/api/activities", params={"account_id": acc["id"]}).json()["total"] >= 1


def test_send_validates_addresses_and_needs_mail(client, smtp, monkeypatch):
    bad = client.post("/api/email/send", data={"to": "not-an-address", "subject": "s", "body": "b"})
    assert bad.status_code == 422 and "not a valid email" in bad.json()["detail"]
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "mail_backend", "disabled")
    assert client.get("/api/email/compose").json()["enabled"] is False
    r = client.post("/api/email/send", data={"to": "a@b.example", "subject": "s", "body": "b"})
    assert r.status_code == 503

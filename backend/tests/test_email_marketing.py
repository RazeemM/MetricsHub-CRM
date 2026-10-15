"""SMTP sending, email templates, mailing lists, campaigns (queue, tracking, unsubscribe) and quotes over SMTP."""
import re
import smtplib
from urllib.parse import parse_qs, urlparse

import pytest

from app import campaigns, mail
from app.config import get_settings
from app.db import SessionLocal
from app.models import Contact


class FakeSMTP:
    sent: list = []
    refuse: set = set()
    down = False

    def send_message(self, msg, from_addr, to_addrs):
        bad = [a for a in to_addrs if a in FakeSMTP.refuse]
        if bad:
            raise smtplib.SMTPRecipientsRefused({a: (550, b"no such user") for a in bad})
        FakeSMTP.sent.append((msg, from_addr, to_addrs))

    def quit(self):
        pass


@pytest.fixture
def smtp(monkeypatch):
    s = get_settings()
    for k, v in {"mail_backend": "smtp", "bulk_mail_backend": "", "smtp_host": "smtp.test", "smtp_port": 587,
                 "mail_from": "news@metricshub.example", "mail_from_name": "MetricsHub",
                 "app_url": "https://crm.test", "bulk_rate_per_minute": 600,
                 "marketing_postal_address": "1 Rue Exemple, Paris"}.items():
        monkeypatch.setattr(s, k, v)
    FakeSMTP.sent, FakeSMTP.refuse, FakeSMTP.down = [], set(), False

    def factory():
        if FakeSMTP.down:
            raise mail.MailError("Could not connect to the SMTP server smtp.test:587")
        return FakeSMTP()

    monkeypatch.setattr(mail, "smtp_factory", factory)
    return FakeSMTP


def _html(msg) -> str:
    return msg.get_body(preferencelist=("html",)).get_content()


def test_smtp_test_message_and_settings(client, smtp):
    st = client.get("/api/mail/settings").json()
    assert st["transactional"]["enabled"] and st["bulk"]["backend"] == "smtp" and st["smtp"]["host"] == "smtp.test"
    assert "password" not in str(st).lower()
    assert client.post("/api/mail/test", json={"to": "admin@metricshub.example"}).status_code == 200
    msg, envelope_from, to = smtp.sent[0]
    assert msg["From"] == "MetricsHub <news@metricshub.example>" and to == ["admin@metricshub.example"]
    assert msg.get_body(preferencelist=("plain",)).get_content().strip().startswith("The CRM can send")


def test_templates_starters_and_preview(client):
    st = client.get("/api/email-templates/starters").json()
    assert {s["key"] for s in st} == {"newsletter", "announcement", "blank"}
    assert all("{postal_address}" in s["body_html"] and "{unsubscribe_url}" in s["body_html"] for s in st)
    t = client.post("/api/email-templates", json={
        "name": "Spring news", "subject": "News for {company}", "preheader": "Hello {first_name}",
        "body_html": "<html><body><p>Hi {first_name|there}, from {owner}</p></body></html>"}).json()
    p = client.post("/api/email-templates/preview", json={"subject": t["subject"], "preheader": t["preheader"],
                                                          "body_html": t["body_html"]}).json()
    assert p["subject"] == "News for Example Customer Ltd" and "Hi Jane, from Your Name" in p["html"]
    assert "Unsubscribe" in p["html"] and "1 Rue" not in p["html"]  # footer added; address only when configured
    evil = client.post("/api/email-templates/preview", json={"subject": "s", "body_html": "<p>{first_name}</p>",
                                                             "contact_id": None}).json()
    assert "<p>Jane</p>" in evil["html"]


def _contact(client, first, email, **extra):
    return client.post("/api/contacts", json={"first_name": first, "email": email, **extra}).json()


def test_lists_campaign_send_track_and_unsubscribe(client, smtp):
    a = _contact(client, "Ada", "ada@leads.example", lifecycle="lead", country="Freedonia")
    b = _contact(client, "<b>Bob</b>", "bob@leads.example", lifecycle="lead", country="Freedonia")
    _contact(client, "Gone", "gone@leads.example", lifecycle="lead", country="Freedonia")
    with SessionLocal() as db:
        db.query(Contact).filter(Contact.email == "gone@leads.example").update({"unsubscribed": True})
        db.commit()
    lst = client.post("/api/lists", json={"name": "Freedonia leads", "kind": "list"}).json()
    r = client.post(f"/api/lists/{lst['id']}/members", json={"filter": {"lifecycle": ["lead"], "country": ["freedonia"]}})
    assert r.json()["added"] == 3
    csv_data = "email,first_name\nnew@csv.example,Nia\nnot-an-email,X\nada@leads.example,Ada\n"
    imp = client.post(f"/api/lists/{lst['id']}/import", files={"file": ("l.csv", csv_data, "text/csv")},
                      data={"consent": "true"}).json()
    assert imp == {"rows": 3, "added": 1, "new_contacts": 1, "invalid_rows": 1}

    t = client.post("/api/email-templates", json={"name": "Promo", "subject": "Hello {first_name|friend}",
                                                  "body_html": '<html><body><p>Hi {first_name}</p>'
                                                               '<a href="https://example.com/offer?x=1&amp;y=2">Offer</a>'
                                                               '</body></html>'}).json()
    c = client.post("/api/campaigns", json={"name": "Spring promo", "template_id": t["id"],
                                            "list_ids": [lst["id"]], "reply_to": "sales@metricshub.example"}).json()
    assert c["subject"] == "Hello {first_name|friend}" and c["status"] == "draft"
    aud = client.get(f"/api/campaigns/{c['id']}/audience").json()
    assert aud["recipients"] == 3 and aud["skipped_by_reason"] == {"unsubscribed from all marketing email": 1}

    assert client.post(f"/api/campaigns/{c['id']}/test", json={"to": ["me@metricshub.example"]}).status_code == 200
    assert smtp.sent[-1][0]["Subject"] == "[TEST] Hello Jane"
    smtp.sent.clear()

    sent = client.post(f"/api/campaigns/{c['id']}/send", json={}).json()
    assert sent["status"] == "sending" and sent["stats"]["queued"] == 3
    assert client.put(f"/api/campaigns/{c['id']}", json={"name": "x"}).status_code == 409  # frozen once started
    smtp.refuse = {"new@csv.example"}
    with SessionLocal() as db:
        campaigns.process(db)
        campaigns.process(db)  # nothing left: marks it sent
    st = client.get(f"/api/campaigns/{c['id']}").json()
    assert st["status"] == "sent" and st["stats"]["sent"] == 2 and st["stats"]["failed"] == 1

    by_to = {m["To"]: m for m, _, _ in smtp.sent}
    ada = by_to["ada@leads.example"]
    assert ada["Subject"] == "Hello Ada" and ada["Reply-To"] == "sales@metricshub.example"
    assert ada["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    raw = ada.as_bytes().decode()
    assert "List-Unsubscribe: <https://crm.test/api/public/unsubscribe/" in raw  # not MIME-encoded
    body = _html(ada)
    assert "&lt;b&gt;" not in body and "1 Rue Exemple, Paris" in body
    assert "&lt;b&gt;Bob&lt;/b&gt;" in _html(by_to["bob@leads.example"])  # merged values are escaped

    # click: signed redirect to the original link; tampering is refused
    link = re.search(r'href="(https://crm\.test/api/t/c/[^"]+)"', body).group(1).replace("&amp;", "&")
    u = urlparse(link)
    r = client.get(u.path, params={k: v[0] for k, v in parse_qs(u.query).items()}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://example.com/offer?x=1&y=2"
    bad = {k: v[0] for k, v in parse_qs(u.query).items()} | {"u": "https://evil.example"}
    assert client.get(u.path, params=bad, follow_redirects=False).status_code == 400
    # open pixel
    pixel = re.search(r'src="https://crm\.test(/api/t/o/[^"]+\.gif)"', body).group(1)
    assert client.get(pixel).headers["content-type"] == "image/gif"

    # unsubscribe: GET only shows a confirmation (mail scanners follow links), POST unsubscribes everywhere
    unsub = re.search(r"<(https://crm\.test(/api/public/unsubscribe/[^>]+))>", ada["List-Unsubscribe"]).group(2)
    assert "Unsubscribe" in client.get(unsub).text
    assert client.get("/api/contacts", params={"q": "ada@leads.example"}).json()["items"][0]["unsubscribed"] is False
    assert client.post(unsub).status_code == 200
    assert client.get("/api/contacts", params={"q": "ada@leads.example"}).json()["items"][0]["unsubscribed"] is True
    members = client.get(f"/api/lists/{lst['id']}/members", params={"q": "ada"}).json()["items"]
    assert members[0]["status"] == "unsubscribed"

    st = client.get(f"/api/campaigns/{c['id']}").json()["stats"]
    assert st["opened"] == 1 and st["clicked"] == 1 and st["unsubscribed"] == 1 and st["open_rate"] == 50.0
    rec = client.get(f"/api/campaigns/{c['id']}/recipients", params={"status": "failed"}).json()["items"]
    assert rec[0]["email"] == "new@csv.example" and "refused" in rec[0]["reason"]
    hist = client.get(f"/api/contacts/{a['id']}/campaigns").json()
    assert hist["campaigns"][0]["name"] == "Spring promo" and hist["lists"][0]["status"] == "unsubscribed"
    assert b["id"]


def test_server_down_pauses_and_keeps_the_queue(client, smtp):
    _contact(client, "Pat", "pat@pause.example")
    lst = client.post("/api/lists", json={"name": "Pause list"}).json()
    client.post(f"/api/lists/{lst['id']}/members", json={"filter": {"lifecycle": ["lead"]}})
    c = client.post("/api/campaigns", json={"name": "Pause test", "subject": "Hi", "body_html": "<p>x</p>",
                                            "list_ids": [lst["id"]]}).json()
    client.post(f"/api/campaigns/{c['id']}/send", json={})
    smtp.down = True
    with SessionLocal() as db:
        campaigns.process(db)
    st = client.get(f"/api/campaigns/{c['id']}").json()
    assert st["status"] == "paused" and "smtp.test" in st["last_error"] and st["stats"]["sent"] == 0
    smtp.down = False
    assert client.post(f"/api/campaigns/{c['id']}/action", json={"action": "resume"}).json()["status"] == "sending"
    with SessionLocal() as db:
        campaigns.process(db)
    assert client.get(f"/api/campaigns/{c['id']}").json()["stats"]["queued"] == 0


def test_newsletters_need_consent_and_schedule(client, smtp):
    yes = _contact(client, "Yes", "yes@news.example", consent_marketing=True)
    _contact(client, "No", "no@news.example")
    lst = client.post("/api/lists", json={"name": "Monthly", "kind": "list"}).json()
    client.post(f"/api/lists/{lst['id']}/members", json={"contact_ids": [yes["id"]]})
    client.post(f"/api/lists/{lst['id']}/import", files={"file": ("n.csv", "email\nno@news.example\n", "text/csv")})
    c = client.post("/api/campaigns", json={"name": "Issue 1", "kind": "newsletter", "subject": "News",
                                            "body_html": "<p>news</p>", "list_ids": [lst["id"]]}).json()
    assert c["require_consent"] is True
    assert client.get(f"/api/campaigns/{c['id']}/audience").json()["skipped_by_reason"] == {"no marketing consent": 1}
    s = client.post(f"/api/campaigns/{c['id']}/send", json={"scheduled_at": "2099-01-01T08:00:00Z"}).json()
    assert s["status"] == "scheduled"
    assert client.post(f"/api/campaigns/{c['id']}/action", json={"action": "unschedule"}).json()["status"] == "draft"


def test_cannot_send_without_bulk_mail(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "mail_backend", "disabled")
    monkeypatch.setattr(get_settings(), "bulk_mail_backend", "")
    lst = client.post("/api/lists", json={"name": "No mail list"}).json()
    c = client.post("/api/campaigns", json={"name": "No mail", "subject": "s", "body_html": "<p>x</p>",
                                            "list_ids": [lst["id"]]}).json()
    assert client.post(f"/api/campaigns/{c['id']}/send", json={}).status_code == 503


def test_campaign_job_releases_its_lock(client, smtp):
    """Run the scheduler job twice: the second run must get the lock again (it used to stay held)."""
    from sqlalchemy import text

    from app import jobs
    from app.db import engine
    jobs.run_campaigns()
    jobs.run_campaigns()
    with engine.connect() as conn:
        held = conn.scalar(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND objid = :id "
                                "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"),
                           {"id": jobs.CAMPAIGN_LOCK_ID})
    assert held == 0

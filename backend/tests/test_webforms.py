"""Website forms: secret (HMAC / token), origins, rate limits, spam, contact upsert, timeline, owner notification and
the newsletter double opt-in."""
import json
import re
import time

import pytest
from sqlalchemy import select

from app import mail, webforms
from app.config import get_settings
from app.db import SessionLocal
from app.models import Activity, Contact, FormSubmission, ListMember, Notification


class FakeSMTP:
    sent: list = []

    def send_message(self, msg, from_addr, to_addrs):
        FakeSMTP.sent.append((msg, from_addr, to_addrs))

    def quit(self):
        pass


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    s = get_settings()
    for k, v in {"mail_backend": "smtp", "bulk_mail_backend": "", "smtp_host": "smtp.test",
                 "mail_from": "news@metricshub.example", "app_url": "https://crm.test", "proxy_hops": 1}.items():
        monkeypatch.setattr(s, k, v)
    FakeSMTP.sent = []
    monkeypatch.setattr(mail, "smtp_factory", FakeSMTP)
    webforms.limiter.hits.clear()


def _form(client, key, **extra):
    r = client.post("/api/web-forms", json={"key": key, "name": key.replace("-", " ").title(), **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _signed(client, form, fields, ip="203.0.113.5", ts=None, secret=None):
    body = json.dumps(fields).encode()
    ts = str(ts or int(time.time()))
    return client.post(f"/api/public/forms/{form['key']}", content=body, headers={
        "Content-Type": "application/json", "X-CRM-Timestamp": ts, "X-Forwarded-For": ip,
        "X-CRM-Signature": "sha256=" + webforms.sign(secret or form["secret"], ts, body)})


def _contact(email) -> Contact:
    with SessionLocal() as db:
        return db.scalar(select(Contact).where(Contact.email == email))


def test_contact_form_creates_then_updates_contact(client, ref):
    me = client.get("/api/auth/me").json()
    acc = client.post("/api/accounts", json={"name": "Acme Corp", "domain": "acme.example"}).json()
    form = _form(client, "contact-us", brand_id=ref["brands"]["METRICSHUB"], lead_source="website_contact",
                 owner_id=me["id"], field_map={"your-email": "email", "fname": "first_name", "org": "company",
                                               "msg": "message", "phone": "phone"})
    assert form["endpoint"] == "https://crm.test/api/public/forms/contact-us" and form["auth_mode"] == "hmac"
    fields = {"your-email": "Jane.Doe@Acme.example", "fname": "Jane", "lastname": "Doe", "org": "Acme",
              "msg": "Please call me about MetricsHub", "utm_campaign": "spring"}

    # refused: no signature, wrong secret, old timestamp
    assert client.post("/api/public/forms/contact-us", json=fields).status_code == 401
    assert _signed(client, form, fields, secret="wrong").status_code == 401
    assert _signed(client, form, fields, ts=int(time.time()) - 3600).status_code == 401
    assert client.post("/api/public/forms/nope", json=fields).status_code == 404
    assert _contact("jane.doe@acme.example") is None

    r = _signed(client, form, fields)
    assert r.status_code == 200 and r.json() == {"ok": True, "status": "accepted"}
    ct = _contact("jane.doe@acme.example")
    assert (ct.first_name, ct.last_name, ct.source, ct.lifecycle) == ("Jane", "Doe", "website_contact", "lead")
    assert ct.account_id == acc["id"] and ct.owner_id == me["id"] and ct.brand_id == ref["brands"]["METRICSHUB"]
    assert not ct.consent_marketing
    with SessionLocal() as db:
        act = db.scalar(select(Activity).where(Activity.contact_id == ct.id))
        assert act.subject == "Web form: Contact Us" and act.account_id == acc["id"]
        assert "msg: Please call me about MetricsHub" in act.body and "utm_campaign: spring" in act.body
        note = db.scalar(select(Notification).where(Notification.user_id == me["id"], Notification.kind == "web_form")
                         .order_by(Notification.id.desc()))
        assert note.title == "Contact Us: Jane Doe (new contact)" and note.link == f"/contacts/{ct.id}"
        assert "Message: Please call me" in note.body
        sub = db.scalar(select(FormSubmission).where(FormSubmission.contact_id == ct.id))
        assert sub.status == "accepted" and sub.contact_created and sub.ip == "203.0.113.5"

    # a second submission fills empty fields but keeps what the CRM already has
    r = _signed(client, form, {**fields, "fname": "Janet", "phone": "+33 1 23 45 67 89"})
    assert r.status_code == 200
    ct2 = _contact("jane.doe@acme.example")
    assert ct2.id == ct.id and ct2.first_name == "Jane" and ct2.phone == "+33 1 23 45 67 89"
    subs = client.get(f"/api/web-forms/{form['id']}/submissions").json()
    assert subs["total"] == 2 and subs["items"][0]["contact_created"] is False
    assert client.get("/api/web-forms").json()[0]["submissions_30d"] >= 2


def test_spam_errors_and_rate_limits(client):
    form = _form(client, "quote", lead_source="quote_request", rate_limit_per_hour=3)
    # honeypot: same answer as a real submission, but nothing is created
    r = _signed(client, form, {"email": "bot@spam.example", "website": "http://spam.example"}, ip="198.51.100.1")
    assert r.json() == {"ok": True, "status": "accepted"} and _contact("bot@spam.example") is None
    r = _signed(client, form, {"email": "bot2@spam.example", "message": "http://a http://b www.c http://d"},
                ip="198.51.100.1")
    assert r.status_code == 200 and _contact("bot2@spam.example") is None
    r = _signed(client, form, {"name": "No Email"}, ip="198.51.100.1")
    assert r.status_code == 422 and r.json()["detail"] == "No email field"
    statuses = [s["status"] for s in client.get(f"/api/web-forms/{form['id']}/submissions").json()["items"]]
    assert statuses == ["error", "spam", "spam"]
    # 3 submissions from that address this hour: the next is refused; another address is fine
    assert _signed(client, form, {"email": "real@corp.example"}, ip="198.51.100.1").status_code == 429
    assert _signed(client, form, {"email": "real@corp.example"}, ip="198.51.100.2").status_code == 200
    assert _contact("real@corp.example").source == "quote_request"
    # the per-address limit across all forms also stops guessing secrets
    webforms.limiter.hits.clear()
    codes = [client.post("/api/public/forms/quote", json={}, headers={"X-Forwarded-For": "192.0.2.9"}).status_code
             for _ in range(webforms.limiter.limit + 1)]
    assert codes[:-1] == [401] * webforms.limiter.limit and codes[-1] == 429


def test_browser_form_token_origin_and_redirect(client):
    form = _form(client, "trial", lead_source="trial", auth_mode="token",
                 allowed_origins=["https://www.metricshub.com/"], redirect_url="https://www.metricshub.com/thanks")
    assert form["allowed_origins"] == ["https://www.metricshub.com"]
    # CORS preflight from the website
    r = client.options("/api/public/forms/trial", headers={
        "Origin": "https://www.metricshub.com", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-crm-form-token"})
    assert r.status_code == 204 and r.headers["access-control-allow-origin"] == "https://www.metricshub.com"
    assert "X-CRM-Form-Token" in r.headers["access-control-allow-headers"]
    # fetch() with the token header
    r = client.post("/api/public/forms/trial", json={"email": "trial@bigco.example", "name": "Tom Trial"},
                    headers={"X-CRM-Form-Token": form["secret"], "Origin": "https://www.metricshub.com"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "https://www.metricshub.com"
    ct = _contact("trial@bigco.example")
    assert (ct.first_name, ct.last_name, ct.source) == ("Tom", "Trial", "trial")
    # another website, or a wrong token
    assert client.post("/api/public/forms/trial", json={"email": "x@bigco.example"}, headers={
        "X-CRM-Form-Token": form["secret"], "Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/public/forms/trial", json={"email": "x@bigco.example"},
                       headers={"X-CRM-Form-Token": "guess"}).status_code == 401
    # a plain HTML form post: token in a hidden field, redirected to the thank-you page
    r = client.post("/api/public/forms/trial", data={"_token": form["secret"], "email": "html@bigco.example"},
                    headers={"Accept": "text/html", "Origin": "https://www.metricshub.com"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "https://www.metricshub.com/thanks"
    assert _contact("html@bigco.example") is not None
    # the HMAC secret mode does not accept the token
    client.put(f"/api/web-forms/{form['id']}", json={**form, "auth_mode": "hmac"})
    assert client.post("/api/public/forms/trial", json={"email": "y@bigco.example"},
                       headers={"X-CRM-Form-Token": form["secret"]}).status_code == 401
    rotated = client.post(f"/api/web-forms/{form['id']}/rotate-secret").json()
    assert rotated["secret"] != form["secret"]


def _confirm_link(msg) -> str:
    html = msg.get_body(preferencelist=("html",)).get_content()
    return re.search(r'href="https://crm\.test(/api/public/confirm/[^"]+)"', html).group(1)


def test_newsletter_double_opt_in(client, ref):
    lst = client.post("/api/lists", json={"name": "MetricsHub News (web)", "kind": "newsletter"}).json()
    form = _form(client, "newsletter", lead_source="newsletter", list_id=lst["id"], auth_mode="token",
                 brand_id=ref["brands"]["METRICSHUB"], notify_owner=False, confirm_redirect_url="https://x.example/ok")
    assert form["list_kind"] == "newsletter"
    r = client.post("/api/public/forms/newsletter", json={"email": "reader@news.example", "first_name": "Rita"},
                    headers={"X-CRM-Form-Token": form["secret"]})
    assert r.json() == {"ok": True, "status": "pending_confirmation"}
    ct = _contact("reader@news.example")
    assert ct.source == "newsletter" and not ct.consent_marketing
    with SessionLocal() as db:
        m = db.scalar(select(ListMember).where(ListMember.contact_id == ct.id))
        assert m.status == "pending" and m.source == "web form"
        sub = db.scalar(select(FormSubmission).where(FormSubmission.contact_id == ct.id))
        assert sub.status == "pending" and sub.note.startswith("Confirmation email for MetricsHub News (web) sent")
    lists = {l["id"]: l for l in client.get("/api/lists").json()}
    assert lists[lst["id"]]["pending"] == 1 and lists[lst["id"]]["subscribed"] == 0

    msg, _, to = FakeSMTP.sent[-1]
    assert to == ["reader@news.example"] and msg["Subject"] == "Please confirm your subscription to MetricsHub News (web)"
    assert "Hello Rita," in msg.get_body(preferencelist=("html",)).get_content()
    link = _confirm_link(msg)
    # opening the link (or a mail scanner following it) does not subscribe
    page = client.get(link)
    assert page.status_code == 200 and '<form method="post">' in page.text
    assert not _contact("reader@news.example").consent_marketing
    # a tampered link is refused
    assert client.post(link[:-1] + ("0" if link[-1] != "0" else "1")).status_code == 400
    r = client.post(link, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "https://x.example/ok"
    ct = _contact("reader@news.example")
    assert ct.consent_marketing and ct.consent_at is not None and not ct.unsubscribed
    with SessionLocal() as db:
        assert db.scalar(select(ListMember.status).where(ListMember.contact_id == ct.id)) == "subscribed"
        assert db.scalar(select(FormSubmission.status).where(FormSubmission.contact_id == ct.id)) == "confirmed"
        assert db.scalar(select(Activity).where(Activity.contact_id == ct.id,
                                                Activity.subject.like("Confirmed newsletter%"))) is not None
    lists = {l["id"]: l for l in client.get("/api/lists").json()}
    assert lists[lst["id"]]["pending"] == 0 and lists[lst["id"]]["subscribed"] == 1

    # signing up again while subscribed sends nothing
    n = len(FakeSMTP.sent)
    r = client.post("/api/public/forms/newsletter", json={"email": "reader@news.example"},
                    headers={"X-CRM-Form-Token": form["secret"]})
    assert r.json()["status"] == "accepted" and len(FakeSMTP.sent) == n
    # after unsubscribing, the old link no longer subscribes
    client.patch(f"/api/lists/{lst['id']}/members/{_member_id(ct.id)}", json={"status": "unsubscribed"})
    assert client.post(link).status_code == 400


def _member_id(contact_id: int) -> int:
    with SessionLocal() as db:
        return db.scalar(select(ListMember.id).where(ListMember.contact_id == contact_id))


def test_consent_checkbox_and_admin_test(client):
    news = client.post("/api/lists", json={"name": "Download readers", "kind": "newsletter"}).json()
    form = _form(client, "download", lead_source="download", list_id=news["id"],
                 field_map={"subscribe": "consent", "mail": "email"})
    # no tick: a lead, but no newsletter email
    r = client.post(f"/api/web-forms/{form['id']}/test", json={"fields": {"mail": "dl1@corp.example"}})
    assert r.status_code == 200 and r.json()["status"] == "accepted" and r.json()["contact_created"]
    assert not FakeSMTP.sent
    # ticked: double opt-in
    r = client.post(f"/api/web-forms/{form['id']}/test", json={"fields": {"mail": "dl2@corp.example",
                                                                          "subscribe": "on"}})
    assert r.json()["status"] == "pending" and FakeSMTP.sent[-1][2] == ["dl2@corp.example"]
    # a plain contact list joins at once
    plain = client.post("/api/lists", json={"name": "Partners from web", "kind": "list"}).json()
    pform = _form(client, "partner", lead_source="partner_signup", list_id=plain["id"])
    client.post(f"/api/web-forms/{pform['id']}/test", json={"fields": {"email": "p@partner.example",
                                                                       "consent": True}})
    ct = _contact("p@partner.example")
    assert ct.consent_marketing and ct.source == "partner_signup"
    with SessionLocal() as db:
        assert db.scalar(select(ListMember.status).where(ListMember.contact_id == ct.id)) == "subscribed"


def test_form_validation(client):
    bad = client.post("/api/web-forms", json={"key": "Bad Key!", "name": "x"})
    assert bad.status_code == 422
    assert client.post("/api/web-forms", json={"key": "ok-key", "name": "x",
                                               "field_map": {"a": "salary"}}).status_code == 422
    assert client.post("/api/web-forms", json={"key": "ok-key", "name": "x",
                                               "allowed_origins": ["https://a.example/page"]}).status_code == 422
    _form(client, "dup")
    assert client.post("/api/web-forms", json={"key": "dup", "name": "again"}).status_code == 409
    meta = client.get("/api/web-forms/meta").json()
    assert "consent" in meta["contact_fields"] and meta["endpoint_base"].endswith("/api/public/forms/")

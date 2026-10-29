"""Website tracking: the script, what it sends, attribution, identifying visitors and the statistics."""
import datetime as dt
import json

from fastapi.testclient import TestClient

from app import tracking
from app.db import SessionLocal
from app.main import app
from app.models import Activity, Contact, TrackingSite, WebEvent, WebVisitor

SITE = "https://www.metricshub.com"


def _site(client, **kw):
    r = client.post("/api/tracking/sites", json={"name": "metricshub.com", "domains": ["https://MetricsHub.com/x"], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _send(site, vid="visitor-0001", sid="session-0001", new_session=True, origin=SITE, **batch):
    body = {"vid": vid, "sid": sid, "new_session": new_session, "events": batch.pop("events", [])}
    return TestClient(app).post(f"/api/public/t/{site['key']}/collect", content=json.dumps(body),
                                headers={"Content-Type": "text/plain", **({"Origin": origin} if origin else {})})


def _visitor(site, vid="visitor-0001"):
    with SessionLocal() as db:
        v = db.query(WebVisitor).join(TrackingSite).filter(TrackingSite.key == site["key"], WebVisitor.vid == vid).one()
        db.expunge(v)
        return v


def test_site_and_script(client):
    site = _site(client, track_params=True, require_consent=True)
    assert site["domains"] == ["metricshub.com"]
    assert site["snippet"] == f'<script src="http://localhost:5173/api/public/t/{site["key"]}.js" async></script>'
    js = TestClient(app).get(f"/api/public/t/{site['key']}.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    assert f'/api/public/t/{site["key"]}/collect' in js.text and '"consent": true' in js.text and "__CONFIG__" not in js.text
    assert "unknown" in TestClient(app).get("/api/public/t/nope.js").text
    assert client.post("/api/tracking/sites", json={"name": "x", "domains": ["not a domain/"]}).status_code == 422
    assert TestClient(app).get("/api/tracking/sites").status_code == 401


def test_collect_attribution_identify_and_stats(client):
    site = _site(client)
    assert _send(site, origin="https://evil.example", events=[{"t": "page", "url": f"{SITE}/"}]).status_code == 403
    assert _send(site, origin=None, events=[{"t": "page", "url": f"{SITE}/"}]).status_code == 403
    assert TestClient(app).post(f"/api/public/t/{site['key']}/collect", content="{bad",
                                headers={"Origin": SITE}).status_code == 400

    landing = f"{SITE}/pricing?utm_source=linkedin&utm_medium=paid_social&utm_campaign=sko27&email=jane@x.com#top"
    r = _send(site, events=[{"t": "page", "url": landing, "title": "Pricing", "ref": "https://www.linkedin.com/feed"}])
    assert r.status_code == 204
    v = _visitor(site)
    assert (v.sessions, v.page_views, v.contact_id) == (1, 1, None)
    assert v.first_touch["source"] == "linkedin" and v.first_touch["campaign"] == "sko27"
    assert v.first_touch["landing"] == f"{SITE}/pricing"
    with SessionLocal() as db:
        ev = db.query(WebEvent).filter(WebEvent.visitor_id == v.id).one()
        assert "email" not in ev.url and ev.name == "Pricing"  # the query string's personal data is not kept

    # same session: no new session, internal referrer; then a custom event
    _send(site, new_session=False, events=[{"t": "page", "url": f"{SITE}/docs", "ref": f"{SITE}/pricing"},
                                           {"t": "event", "url": f"{SITE}/docs", "name": "Downloaded datasheet",
                                            "props": {"product": "Hardware Sentry", "nested": {"x": 1}}}])
    v = _visitor(site)
    assert (v.sessions, v.page_views) == (1, 2)

    # a later visit from Google search becomes the latest touch, the first one stays
    _send(site, sid="session-0002", events=[{"t": "page", "url": f"{SITE}/", "ref": "https://www.google.fr/"}])
    v = _visitor(site)
    assert v.sessions == 2 and v.last_touch["source"] == "google" and v.last_touch["medium"] == "organic"
    assert v.first_touch["source"] == "linkedin"

    # a form with an email field identifies the visitor; unknown fields are ignored
    _send(site, sid="session-0002", new_session=False, events=[{"t": "identify", "url": f"{SITE}/contact?x=1",
          "form": "contact-form", "fields": {"Email": "Tracked.Jane@helixops.ai", "First name": "Jane",
                                             "company": "Helixops", "newsletter": "true", "favourite_colour": "red"}}])
    with SessionLocal() as db:
        ct = db.query(Contact).filter(Contact.email == "tracked.jane@helixops.ai").one()
        assert ct.first_name == "Jane" and ct.source == "website_contact" and ct.consent_marketing
        assert ct.extra["web"]["original"]["source"] == "linkedin" and ct.extra["web"]["latest"]["source"] == "google"
        assert ct.extra["company"] == "Helixops" and "favourite_colour" not in json.dumps(ct.extra)
        assert db.query(WebEvent).filter(WebEvent.visitor_id == v.id, WebEvent.contact_id.is_(None)).count() == 0
        note = db.query(Activity).filter(Activity.contact_id == ct.id, Activity.subject == "Website: metricshub.com").one()
        assert "form on /contact" in note.body and "linkedin / paid_social" in note.body
        contact_id = ct.id

    web = client.get(f"/api/contacts/{contact_id}/web").json()
    assert web["tracked"] and web["sessions"] == 2 and web["page_views"] == 3
    assert [e["kind"] for e in web["events"]][:2] == ["identify", "page"]
    event = next(e for e in web["events"] if e["kind"] == "event")
    assert event["name"] == "Downloaded datasheet" and event["props"] == {"product": "Hardware Sentry"}

    ov = client.get(f"/api/tracking/sites/{site['id']}/overview").json()
    assert ov["visitors"] == 1 and ov["identified"] == 1 and ov["page_views"] == 3 and ov["sessions"] == 2
    assert ov["top_events"] == [{"name": "Downloaded datasheet", "count": 1}]
    assert ov["top_sources"][0]["source"] == "linkedin / paid_social"
    assert ov["recent_contacts"][0]["email"] == "tracked.jane@helixops.ai" and ov["last_hit_url"] == f"{SITE}/"

    # identifying with an invalid email does nothing
    assert _send(site, vid="visitor-0002", events=[{"t": "identify", "fields": {"email": "nope"}}]).status_code == 204
    assert _visitor(site, "visitor-0002").contact_id is None


def test_touch_rules():
    site = TrackingSite(domains=["metricshub.com"], track_utm=True, track_params=True)
    t = lambda url, ref=None: tracking.touch(site, url, ref)  # noqa: E731
    assert t(f"{SITE}/")["source"] == "direct"
    assert t(f"{SITE}/", f"{SITE}/blog")["source"] == "direct"  # internal referrer
    assert t(f"{SITE}/", "https://docs.metricshub.com/")["source"] == "direct"  # subdomain is internal too
    assert t(f"{SITE}/", "https://duckduckgo.com/")["medium"] == "organic"
    assert t(f"{SITE}/", "https://lnkd.in/abc")["source"] == "linkedin"
    assert t(f"{SITE}/", "https://partner.example.org/post")["medium"] == "referral"
    paid = t(f"{SITE}/?gclid=abc123&utm_term=hardware")
    assert (paid["source"], paid["medium"], paid["gclid"], paid["utm_term"]) == ("google", "cpc", "abc123", "hardware")
    site.track_utm = False
    assert t(f"{SITE}/?utm_source=x", "https://www.bing.com/")["source"] == "bing"  # UTM ignored when turned off


def test_inactive_site_prune_and_integration_check(client):
    site = _site(client, domains=["localhost"])
    assert _send(site, origin="http://localhost:8080", events=[{"t": "page", "url": "http://localhost:8080/"}]).status_code == 204
    check = client.post(f"/api/tracking/sites/{site['id']}/check").json()
    assert not check["results"][0]["found"] and "not a public web address" in check["results"][0]["message"]
    assert check["last_hit_url"] == "http://localhost:8080/"

    with SessionLocal() as db:
        v = db.query(WebVisitor).filter(WebVisitor.site_id == site["id"]).one()
        db.query(WebEvent).filter(WebEvent.visitor_id == v.id).update(
            {"created_at": dt.datetime.now(dt.UTC) - dt.timedelta(days=500)})
        v.last_seen = dt.datetime.now(dt.UTC) - dt.timedelta(days=500)
        db.commit()
        assert tracking.prune(db, 395) == 1
        db.commit()
        assert db.query(WebVisitor).filter(WebVisitor.site_id == site["id"]).count() == 0

    client.patch(f"/api/tracking/sites/{site['id']}", json={"active": False})
    assert _send(site, origin="http://localhost:8080", events=[{"t": "page", "url": "http://localhost:8080/"}]).status_code == 404
    assert client.delete(f"/api/tracking/sites/{site['id']}").status_code == 204


def test_malformed_addresses_are_ignored():
    site = TrackingSite(domains=["metricshub.com"], track_utm=True, track_params=False)
    assert tracking.clean_url("http://[broken/") is None
    assert not tracking.host_allowed(site, "http://[broken")
    assert tracking.touch(site, "http://[broken/?utm_source=x", "https://[bad")["source"] == "direct"

"""End-to-end SSO test against a fake OpenID Connect provider."""
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import get_settings
from app.routers import sso

ISSUER = "https://login.example.com/tenant/v2.0"


@pytest.fixture
def idp(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    s = get_settings()
    monkeypatch.setattr(s, "oidc_issuer", ISSUER)
    monkeypatch.setattr(s, "oidc_client_id", "crm-client")
    monkeypatch.setattr(s, "oidc_client_secret", "secret")
    monkeypatch.setattr(s, "oidc_auto_provision_domains", "metricshub.com")
    meta = {"issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
            "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/keys"}
    monkeypatch.setattr(sso, "_discovery", lambda issuer: meta)

    class FakeJwks:
        def get_signing_key_from_jwt(self, _):
            return type("K", (), {"key": key.public_key()})()

    monkeypatch.setattr(sso, "_jwks_client", lambda uri: FakeJwks())
    state = {"claims": {}}

    def fake_post(url, data, timeout):
        nonce = state["nonce"]
        claims = {"iss": ISSUER, "aud": "crm-client", "sub": "abc-123", "nonce": nonce,
                  "iat": int(time.time()), "exp": int(time.time()) + 300, **state["claims"]}
        token = jwt.encode(claims, key, algorithm="RS256")
        return httpx.Response(200, json={"id_token": token}, request=httpx.Request("POST", url))

    monkeypatch.setattr(sso.httpx, "post", fake_post)
    return state


def _login(client, idp, claims):
    idp["claims"] = claims
    r = client.get("/api/auth/sso/login", follow_redirects=False)
    assert r.status_code == 302
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"]
    idp["nonce"] = q["nonce"][0]
    return client.get("/api/auth/sso/callback", params={"code": "c0de", "state": q["state"][0]},
                      follow_redirects=False)


def test_config_reports_sso(client, idp):
    cfg = client.get("/api/auth/config").json()
    assert cfg["sso_enabled"] and cfg["password_login_enabled"]


def test_sso_auto_provision_and_token(client, idp):
    r = _login(client, idp, {"email": "new.rep@metricshub.com", "name": "New Rep"})
    loc = r.headers["location"]
    assert "/sso#token=" in loc, loc
    token = loc.split("#token=")[1]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "new.rep@metricshub.com" and me["role"] == "sales"


def test_sso_rejects_unknown_domain(client, idp):
    r = _login(client, idp, {"email": "someone@gmail.com", "sub": "zzz"})
    assert "sso_error" in r.headers["location"]


def test_sso_rejects_bad_state(client, idp):
    client.get("/api/auth/sso/login", follow_redirects=False)
    r = client.get("/api/auth/sso/callback", params={"code": "x", "state": "forged"}, follow_redirects=False)
    assert "sso_error" in r.headers["location"]


def _sso_error(r) -> str:
    from urllib.parse import parse_qs, urlparse
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)["sso_error"][0]


def test_unreachable_or_wrong_issuer_shows_a_message_not_500(client, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "oidc_issuer", "https://login.microsoftonline.com/tenant-x/v2.0")
    monkeypatch.setattr(s, "oidc_client_id", "crm-client")
    sso._discovery.cache_clear()

    def down(url, timeout):
        raise httpx.ConnectError("Name or service not known", request=httpx.Request("GET", url))
    monkeypatch.setattr(sso.httpx, "get", down)
    msg = _sso_error(client.get("/api/auth/sso/login", follow_redirects=False))
    assert "cannot reach login.microsoftonline.com" in msg and "ConnectError" in msg

    def bad_tenant(url, timeout):
        return httpx.Response(400, json={"error": "invalid_tenant"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(sso.httpx, "get", bad_tenant)
    msg = _sso_error(client.get("/api/auth/sso/login", follow_redirects=False))
    assert "HTTP 400" in msg and "CRM_OIDC_ISSUER" in msg
    sso._discovery.cache_clear()


def test_refused_code_exchange_shows_the_provider_reason(client, idp, monkeypatch):
    def refuse(url, data, timeout):
        return httpx.Response(401, json={"error": "invalid_client", "error_description":
                                         "AADSTS7000215: Invalid client secret provided.\r\nTrace ID: x"},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(sso.httpx, "post", refuse)
    r = client.get("/api/auth/sso/login", follow_redirects=False)
    from urllib.parse import parse_qs, urlparse
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    msg = _sso_error(client.get("/api/auth/sso/callback", params={"code": "c", "state": state}, follow_redirects=False))
    assert msg == "The identity provider refused the sign-in: AADSTS7000215: Invalid client secret provided."


def test_issuer_without_https_is_explained(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "oidc_issuer", "//login.microsoftonline.com/tenant-x/v2.0")
    monkeypatch.setattr(get_settings(), "oidc_client_id", "crm-client")
    msg = _sso_error(client.get("/api/auth/sso/login", follow_redirects=False))
    assert msg.startswith("CRM_OIDC_ISSUER must start with https://")


def test_default_role_spellings_are_normalized():
    from app.config import Settings, normalize_role

    assert [normalize_role(v) for v in ("Read-only", "READ ONLY", "Sales", "admin", "manager", "")] ==         ["readonly", "readonly", "sales", "admin", "readonly", "readonly"]
    assert Settings(oidc_default_role="Read-only").oidc_default_role == "readonly"

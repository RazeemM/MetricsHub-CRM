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

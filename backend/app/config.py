from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROLES = ("admin", "sales", "readonly")


def normalize_role(value: str | None, fallback: str = "readonly") -> str:
    """'Read-only', 'READ ONLY', 'Sales' ... -> a role the CRM knows; anything else -> fallback."""
    key = "".join(ch for ch in (value or "").lower() if ch.isalpha())
    return key if key in ROLES else fallback


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")

    database_url: str = "postgresql+psycopg://crm:crm@localhost:5432/crm"
    secret_key: str = "dev-only-secret-change-me-in-production-please"
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173"

    # First administrator, created on startup if no user exists
    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"
    admin_name: str = "Administrator"

    # Public URL of the web app (used for SSO redirects)
    app_url: str = "http://localhost:5173"
    password_login_enabled: bool = True

    # Single sign-on (OpenID Connect): Microsoft Entra ID, Google, Okta, Keycloak...
    # Entra ID issuer: https://login.microsoftonline.com/<tenant-id>/v2.0
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid email profile"
    oidc_button_label: str = "Sign in with Microsoft"
    # Comma-separated email domains allowed to auto-create an account on first SSO login (empty = invite only)
    oidc_auto_provision_domains: str = ""
    oidc_default_role: str = "sales"  # admin, sales or readonly ("Read-only" is accepted too)

    @field_validator("oidc_default_role")
    @classmethod
    def known_role(cls, v: str) -> str:
        return normalize_role(v)

    @property
    def sso_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id)

    # Outgoing email (quotes): "disabled", "graph" (Microsoft 365) or "log" (kept in memory, nothing sent)
    mail_backend: str = "disabled"
    # Microsoft Graph app registration; empty = reuse the SSO app (tenant taken from oidc_issuer)
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    # Send every email from this mailbox (e.g. sales@metricshub.com) instead of the signed-in user's own.
    # Required for SMTP, which always sends from it (replies still go to the user who sent a quote).
    mail_from: str = ""
    mail_from_name: str = ""
    # Campaigns and newsletters: "" = same backend as above, or smtp / graph / log / disabled
    bulk_mail_backend: str = ""
    bulk_rate_per_minute: int = 120  # stay under your provider's sending limit
    # SMTP server (CRM_MAIL_BACKEND=smtp and/or CRM_BULK_MAIL_BACKEND=smtp)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_security: str = "starttls"  # starttls (port 587), ssl (port 465) or none
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_envelope_from: str = ""  # bounce address, if different from CRM_MAIL_FROM
    # Physical address shown in every campaign footer (required by anti-spam laws such as CAN-SPAM)
    marketing_postal_address: str = ""

    # Website forms: how many reverse proxies in front of the API add to X-Forwarded-For (the web container's nginx
    # is one; add one per TLS proxy such as Caddy or a load balancer). Used to find the visitor's IP for rate limiting.
    proxy_hops: int = 1

    # Days before contract end when a renewal opportunity is opened
    renewal_lead_days: int = 120
    # Days before a licence's renewal date when its owner is notified (about 2 months)
    renewal_notice_days: int = 60
    # Run the daily renewal check inside the API process (disable when running it from cron instead)
    run_scheduler: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()

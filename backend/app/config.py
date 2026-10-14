from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    oidc_default_role: str = "sales"

    @property
    def sso_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id)

    # Days before contract end when a renewal opportunity is opened
    renewal_lead_days: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()

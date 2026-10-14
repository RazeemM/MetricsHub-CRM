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

    # Days before contract end when a renewal opportunity is opened
    renewal_lead_days: int = 120


@lru_cache
def get_settings() -> Settings:
    return Settings()

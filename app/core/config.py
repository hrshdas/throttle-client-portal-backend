from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://throttle:throttle123@localhost:5432/throttle"
    SECRET_KEY: str = "dev-secret-key-change-in-production-minimum-64-chars-long-xxxx"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ENVIRONMENT: str = "development"
    FRONTEND_URL: str = "http://localhost:8080"

    # SMTP (optional)
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""

    # ─── Meta Marketing API ────────────────────────────────────────────────────
    # Set these in .env — NEVER hardcode real values here.
    META_APP_ID: str = "placeholder_meta_app_id"
    META_APP_SECRET: str = "placeholder_meta_app_secret"
    # API version — update as Meta releases new versions. Current latest: v26.0
    META_API_VERSION: str = "v26.0"
    # OAuth redirect URI — must exactly match the URI registered in Meta App Dashboard
    META_REDIRECT_URI: str = "http://localhost:8000/api/v1/meta/connect/callback"
    # Dedicated encryption key for Meta tokens. If empty, falls back to SECRET_KEY derivation.
    # Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    META_ENCRYPTION_KEY: str = ""
    # OAuth CSRF state validity window (seconds)
    META_OAUTH_STATE_TTL_SECONDS: int = 600
    # Historical sync window (days back from today)
    META_HISTORICAL_DAYS: int = 30
    # Recurring sync interval in minutes
    META_SYNC_INTERVAL_MINUTES: int = 30
    # ──────────────────────────────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def meta_is_configured(self) -> bool:
        """True only when real (non-placeholder) Meta credentials are present."""
        return (
            self.META_APP_ID not in ("placeholder_meta_app_id", "123456789012345", "")
            and self.META_APP_SECRET not in ("placeholder_meta_app_secret", "meta_dev_app_secret_998877", "")
        )

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()

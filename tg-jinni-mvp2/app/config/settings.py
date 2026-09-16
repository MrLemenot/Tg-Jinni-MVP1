from functools import lru_cache
import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables / local .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    bot_token: str
    database_url: str
    webapp_url: str = ""
    admin_ids: str = ""
    payment_provider_token: str | None = None
    payment_webhook_secret: str | None = None
    ownership_recheck_hours: int = 24
    task_hold_hours: int = 48
    promotion_package_price_rub: int = 180
    promotion_package_impressions: int = 4500
    environment: str = "development"

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, value: str) -> str:
        value = value.strip()
        if not value or value.lower() in {"change_me", "changeme", "your_bot_token"}:
            raise ValueError("BOT_TOKEN is required and must not be a placeholder")
        if ":" not in value:
            raise ValueError("BOT_TOKEN does not look like a Telegram bot token")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("DATABASE_URL is required")
        return value

    @property
    def public_webapp_url(self) -> str:
        value = self.webapp_url.strip() or os.getenv("RENDER_EXTERNAL_URL", "").strip()
        return value.rstrip("/")

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_ids.split(",") if x.strip()}

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()

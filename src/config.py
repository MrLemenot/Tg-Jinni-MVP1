from __future__ import annotations

from dataclasses import dataclass


def _text(value: object | None, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _int(value: object | None, default: int) -> int:
    try:
        return int(_text(value))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class Config:
    bot_token: str
    webhook_secret: str
    payment_provider_token: str
    admin_ids: frozenset[int]
    task_hold_hours: int = 48
    ownership_recheck_hours: int = 24
    promotion_price_rub: int = 180
    promotion_impressions: int = 4500
    environment: str = "production"

    @classmethod
    def from_env(cls, env) -> "Config":
        raw_admins = _text(getattr(env, "ADMIN_IDS", ""))
        admin_ids: set[int] = set()
        for part in raw_admins.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                admin_ids.add(int(part))
            except ValueError:
                continue
        return cls(
            bot_token=_text(getattr(env, "BOT_TOKEN", "")),
            webhook_secret=_text(getattr(env, "TELEGRAM_WEBHOOK_SECRET", "")),
            payment_provider_token=_text(getattr(env, "PAYMENT_PROVIDER_TOKEN", "")),
            admin_ids=frozenset(admin_ids),
            task_hold_hours=max(1, _int(getattr(env, "TASK_HOLD_HOURS", None), 48)),
            ownership_recheck_hours=max(1, _int(getattr(env, "OWNERSHIP_RECHECK_HOURS", None), 24)),
            promotion_price_rub=max(1, _int(getattr(env, "PROMOTION_PACKAGE_PRICE_RUB", None), 180)),
            promotion_impressions=max(1, _int(getattr(env, "PROMOTION_PACKAGE_IMPRESSIONS", None), 4500)),
            environment=_text(getattr(env, "ENVIRONMENT", None), "production"),
        )

    def require_bot_token(self) -> str:
        if not self.bot_token or ":" not in self.bot_token:
            raise RuntimeError("BOT_TOKEN is not configured")
        return self.bot_token

    def require_webhook_secret(self) -> str:
        if not self.webhook_secret:
            raise RuntimeError("TELEGRAM_WEBHOOK_SECRET is not configured")
        return self.webhook_secret

    def require_payment_token(self) -> str:
        if not self.payment_provider_token:
            raise RuntimeError("PAYMENT_PROVIDER_TOKEN is not configured")
        return self.payment_provider_token

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException

from app.config.settings import get_settings


def validate_telegram_init_data(init_data: str, max_age: int = 86400) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram initData")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing Telegram initData hash")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Telegram auth_date")
    if auth_date <= 0 or time.time() - auth_date > max_age:
        raise HTTPException(status_code=401, detail="Telegram initData expired")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", get_settings().bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    try:
        user = json.loads(pairs["user"])
        if not isinstance(user, dict) or "id" not in user:
            raise ValueError
        return user
    except (KeyError, json.JSONDecodeError, ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid Telegram user payload")


async def current_user(
    init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data"),
) -> dict:
    return validate_telegram_init_data(init_data or "")


async def current_user_id(user: dict = Depends(current_user)) -> int:
    try:
        return int(user["id"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid Telegram user")

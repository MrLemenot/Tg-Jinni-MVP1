from __future__ import annotations

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException, Request

MAX_INIT_DATA_AGE_SECONDS = 3600


def validate_telegram_init_data(init_data: str, bot_token: str, max_age: int = MAX_INIT_DATA_AGE_SECONDS) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram initData")
    if not bot_token or ":" not in bot_token:
        raise HTTPException(status_code=503, detail="Telegram authentication is not configured")

    pairs_list = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    pairs = {k: v for k, v in pairs_list}
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing Telegram initData hash")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram auth_date") from exc

    if auth_date <= 0 or time.time() - auth_date > max_age:
        raise HTTPException(status_code=401, detail="Telegram initData expired")
    if auth_date - time.time() > 60:
        raise HTTPException(status_code=401, detail="Telegram initData is from the future")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")

    try:
        user = json.loads(pairs["user"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram user payload") from exc
    if not isinstance(user, dict) or "id" not in user:
        raise HTTPException(status_code=401, detail="Invalid Telegram user payload")
    return user


async def current_user(request: Request, init_data: str | None = Header(default=None, alias="X-Telegram-Init-Data")) -> dict:
    env = request.scope["env"]
    return validate_telegram_init_data(init_data or "", str(getattr(env, "BOT_TOKEN", "")))


async def current_user_id(user: dict = Depends(current_user)) -> int:
    try:
        return int(user["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid Telegram user") from exc

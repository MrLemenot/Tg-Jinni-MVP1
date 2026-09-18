from __future__ import annotations

import json

from workers import fetch


class TelegramError(RuntimeError):
    pass


async def call(env, method: str, payload: dict | None = None) -> dict:
    token = str(getattr(env, "BOT_TOKEN", ""))
    if not token or ":" not in token:
        raise TelegramError("BOT_TOKEN is not configured")
    response = await fetch(
        f"https://api.telegram.org/bot{token}/{method}",
        method="POST",
        headers={"content-type": "application/json; charset=utf-8"},
        body=json.dumps(payload or {}, ensure_ascii=False),
    )
    try:
        data = await response.json()
    except Exception as exc:  # pragma: no cover - remote failure path
        raise TelegramError(f"Telegram returned non-JSON response for {method}") from exc
    if not data.get("ok"):
        raise TelegramError(str(data.get("description") or f"Telegram API error in {method}"))
    return data.get("result")


async def get_chat(env, username: str) -> dict:
    return await call(env, "getChat", {"chat_id": username})


async def get_chat_member(env, chat_id: int, user_id: int) -> dict:
    return await call(env, "getChatMember", {"chat_id": chat_id, "user_id": user_id})


async def get_me(env) -> dict:
    return await call(env, "getMe")


async def send_message(env, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return await call(env, "sendMessage", payload)


async def answer_pre_checkout(env, query_id: str, ok: bool, error_message: str | None = None) -> bool:
    payload = {"pre_checkout_query_id": query_id, "ok": ok}
    if not ok and error_message:
        payload["error_message"] = error_message[:200]
    await call(env, "answerPreCheckoutQuery", payload)
    return True


async def create_invoice_link(env, *, title: str, description: str, payload: str, amount_rub: int) -> str:
    result = await call(
        env,
        "createInvoiceLink",
        {
            "title": title[:32],
            "description": description[:255],
            "payload": payload,
            "provider_token": str(getattr(env, "PAYMENT_PROVIDER_TOKEN", "")),
            "currency": "RUB",
            "prices": [{"label": "Продвижение", "amount": int(amount_rub) * 100}],
        },
    )
    return str(result)

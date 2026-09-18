from __future__ import annotations

from html import escape

from config import Config
from db import Database
from telegram_api import answer_pre_checkout, call, create_invoice_link, send_message


async def handle_update(env, update: dict, public_base_url: str) -> None:
    cfg = Config.from_env(env)

    if "pre_checkout_query" in update:
        query = update["pre_checkout_query"]
        payload = str(query.get("invoice_payload", ""))
        db = Database(env)
        async with db.connection() as conn:
            payment = await conn.fetchrow(
                """
                SELECT p.id, p.status, p.amount, p.currency, pc.id AS campaign_id
                FROM payments p
                LEFT JOIN promotion_campaigns pc ON pc.id = p.campaign_id
                WHERE p.invoice_payload = $1
                """,
                payload,
            )
        valid = bool(
            payment
            and payment["status"] == "pending"
            and payment["currency"] == "RUB"
            and int(payment["amount"]) * 100 == int(query.get("total_amount") or -1)
        )
        await answer_pre_checkout(
            env,
            str(query["id"]),
            valid,
            None if valid else "Счёт больше недействителен. Создайте новый счёт.",
        )
        return

    message = update.get("message")
    if not message:
        return

    from_user = message.get("from") or {}
    user_id = int(from_user.get("id", 0))
    if not user_id:
        return

    db = Database(env)
    async with db.transaction() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name, updated_at=NOW()
            """,
            user_id,
            from_user.get("username"),
            from_user.get("first_name"),
        )

    successful_payment = message.get("successful_payment")
    if successful_payment:
        await _handle_successful_payment(env, successful_payment, user_id)
        return

    text = str(message.get("text") or "").strip()
    if text.startswith("/start"):
        base = (public_base_url or "").rstrip("/")
        keyboard = {
            "inline_keyboard": [
                [{"text": "🎮 Открыть TG-Jinni", "web_app": {"url": base + "/"}}],
                [{"text": "🎁 Задания", "web_app": {"url": base + "/?screen=tasks"}}],
                [{"text": "📺 Мои каналы", "web_app": {"url": base + "/?screen=channels"}}],
            ]
        }
        await send_message(
            env,
            user_id,
            "🧞‍♂️ TG-Jinni\n\nИграй, выполняй задания, получай монеты и продвигай свои Telegram-каналы.",
            keyboard,
        )
        return

    if text.startswith("/tasks"):
        base = (public_base_url or "").rstrip("/")
        await send_message(
            env,
            user_id,
            "🎁 Задания открываются в Mini App.",
            {"inline_keyboard": [[{"text": "Открыть задания", "web_app": {"url": base + "/?screen=tasks"}}]]},
        )


async def _handle_successful_payment(env, payment: dict, user_id: int) -> None:
    payload = str(payment.get("invoice_payload", ""))
    provider_charge_id = str(payment.get("provider_payment_charge_id") or "")
    telegram_charge_id = str(payment.get("telegram_payment_charge_id") or "")
    db = Database(env)
    cfg = Config.from_env(env)
    paid_currency = str(payment.get("currency") or "")
    paid_total_amount = int(payment.get("total_amount") or -1)
    if paid_currency != "RUB":
        return

    async with db.transaction() as conn:
        row = await conn.fetchrow(
            """
            SELECT p.id, p.status, p.amount, p.currency, p.campaign_id, p.telegram_id, pc.entity_id
            FROM payments p
            JOIN promotion_campaigns pc ON pc.id = p.campaign_id
            WHERE p.invoice_payload = $1
            FOR UPDATE
            """,
            payload,
        )
        if not row or row["telegram_id"] != user_id:
            return
        if row["currency"] != paid_currency or paid_total_amount != int(row["amount"]) * 100:
            return
        if row["status"] == "paid":
            return
        if row["status"] != "pending":
            return
        await conn.execute(
            """
            UPDATE payments
            SET status='paid', provider_payment_id=$2, paid_at=NOW()
            WHERE id=$1
            """,
            row["id"],
            (telegram_charge_id or provider_charge_id)[:255] or None,
        )
        await conn.execute(
            """
            UPDATE promotion_campaigns
            SET status='active', started_at=COALESCE(started_at, NOW())
            WHERE id=$1
            """,
            row["campaign_id"],
        )
        await conn.execute(
            "UPDATE entities SET is_promoted=TRUE WHERE id=$1",
            row["entity_id"],
        )
        entity = await conn.fetchrow("SELECT id, title, username, telegram_chat_id FROM entities WHERE id=$1", row["entity_id"])
        if entity and entity["telegram_chat_id"]:
            await conn.execute(
                """
                INSERT INTO tasks (title, description, task_type, entity_id, channel_username, channel_id, reward_coins, hold_hours, is_active)
                SELECT $1, 'Подпишись на канал и подтверди подписку в TG-Jinni.', 'subscription', $2, $3, $4, 50, $5, TRUE
                WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE entity_id=$2 AND task_type='subscription' AND is_active=TRUE)
                """,
                f"Подписка на {entity['title']}",
                entity["id"],
                entity["username"],
                entity["telegram_chat_id"],
                cfg.task_hold_hours,
            )

    await send_message(env, user_id, "✅ Платёж получен. Продвижение канала запущено.")

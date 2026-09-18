from __future__ import annotations

import hmac
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from workers import WorkerEntrypoint, asgi

from auth import current_user, current_user_id
from bot import handle_update
from config import Config
from db import Database, db_from_request
from game_engine import BayesianGameEngine, Candidate
from telegram_api import (
    TelegramError,
    answer_pre_checkout,
    call,
    create_invoice_link,
    get_chat,
    get_chat_member,
    get_me,
    send_message,
)

app = FastAPI(title="TG-Jinni API", version="5.1.0")


class AnswerRequest(BaseModel):
    question_id: int
    answer: float = Field(ge=0, le=1)


class ProposeEntity(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=2, max_length=128)


class CreatePromotion(BaseModel):
    entity_id: int


class ModerationComment(BaseModel):
    comment: str | None = Field(default=None, max_length=1000)


class EntityReport(BaseModel):
    reason: str | None = Field(default=None, max_length=64)


MAX_QUESTIONS = 20
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def cfg(request: Request) -> Config:
    return Config.from_env(request.scope["env"])


def admin_required(request: Request, user_id: int = Depends(current_user_id)) -> int:
    if user_id not in cfg(request).admin_ids:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user_id


async def ensure_user(conn, user_id: int, username: str | None = None, first_name: str | None = None) -> None:
    await conn.execute(
        """
        INSERT INTO users (telegram_id, username, first_name)
        VALUES ($1, $2, $3)
        ON CONFLICT (telegram_id) DO UPDATE SET
            username=COALESCE($2, users.username),
            first_name=COALESCE($3, users.first_name),
            updated_at=NOW()
        """,
        user_id,
        username,
        first_name,
    )


def normalize_public_username(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if parsed.scheme in {"https", "http"} and parsed.netloc.lower() in {"t.me", "telegram.me"}:
        path = parsed.path.strip("/")
        if "/" in path or path.startswith("+"):
            raise HTTPException(400, "Для проверки канала нужен публичный @username, а не invite-ссылка")
        value = path
    value = value.strip().lstrip("@")
    if not USERNAME_RE.fullmatch(value):
        raise HTTPException(400, "Некорректный публичный username канала")
    return "@" + value.lower()


def member_is_owner(member: dict) -> bool:
    return str(member.get("status", "")) in {"administrator", "creator"}


def member_is_subscribed(member: dict) -> bool:
    status = str(member.get("status", ""))
    if status in {"member", "administrator", "creator"}:
        return True
    if status == "restricted":
        return bool(member.get("is_member"))
    return False


async def load_game_data(conn):
    entities = await conn.fetch(
        """
        SELECT id, title, username
        FROM entities
        WHERE is_active=TRUE AND entity_type='channel'
        ORDER BY id
        """
    )
    questions = await conn.fetch(
        "SELECT id, text FROM questions WHERE is_active=TRUE ORDER BY id LIMIT $1",
        MAX_QUESTIONS,
    )
    if not entities or not questions:
        raise HTTPException(503, "Для игры нужны хотя бы один одобренный канал и активные вопросы")
    weights_rows = await conn.fetch("SELECT entity_id, question_id, weight FROM entity_question_weights")
    weights = {(int(r["entity_id"]), int(r["question_id"])): float(r["weight"]) for r in weights_rows}
    prior = 1.0 / len(entities)
    candidates = [
        Candidate(
            int(entity["id"]),
            prior,
            {int(q["id"]): weights.get((int(entity["id"]), int(q["id"])), 0.5) for q in questions},
        )
        for entity in entities
    ]
    return entities, questions, BayesianGameEngine(candidates)


async def serve_asset(request: Request, path: str = ""):
    env = request.scope["env"]
    asset_path = path.strip("/") or "index.html"
    asset_response = await env.ASSETS.fetch(f"https://assets.local/{asset_path}")
    body = await asset_response.bytes()
    content_type = asset_response.headers.get("content-type") or "application/octet-stream"
    return Response(content=body, status_code=asset_response.status, headers={"content-type": content_type})


@app.get("/healthcheck")
async def healthcheck(request: Request):
    try:
        async with db_from_request(request).connection() as conn:
            await conn.fetchval("SELECT 1")
        return {"status": "ok", "database": "ok", "runtime": "cloudflare-python-workers"}
    except Exception as exc:
        raise HTTPException(503, detail={"status": "degraded", "database": "error"}) from exc


@app.get("/api/v1/me")
async def me(request: Request, telegram_user: dict = Depends(current_user), user_id: int = Depends(current_user_id)):
    async with db_from_request(request).transaction() as conn:
        await ensure_user(conn, user_id, telegram_user.get("username"), telegram_user.get("first_name"))
        row = await conn.fetchrow(
            "SELECT telegram_id, username, first_name, coins_available, coins_hold, games_played, games_won FROM users WHERE telegram_id=$1",
            user_id,
        )
    data = dict(row)
    data["is_admin"] = user_id in cfg(request).admin_ids
    return data


@app.get("/api/v1/shop")
async def shop(request: Request, _user_id: int = Depends(current_user_id)):
    async with db_from_request(request).connection() as conn:
        rows = await conn.fetch(
            "SELECT id, title, description, item_type, price_coins FROM shop_items WHERE is_active=TRUE ORDER BY id"
        )
    return [dict(r) for r in rows]


@app.post("/api/v1/shop/{item_id}/buy")
async def buy_shop_item(item_id: int, request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).transaction() as conn:
        await ensure_user(conn, user_id)
        item = await conn.fetchrow("SELECT * FROM shop_items WHERE id=$1 AND is_active=TRUE FOR UPDATE", item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        user = await conn.fetchrow("SELECT coins_available FROM users WHERE telegram_id=$1 FOR UPDATE", user_id)
        if int(user["coins_available"]) < int(item["price_coins"]):
            raise HTTPException(400, "Недостаточно монет")
        await conn.execute(
            "UPDATE users SET coins_available=coins_available-$2, updated_at=NOW() WHERE telegram_id=$1",
            user_id,
            int(item["price_coins"]),
        )
        await conn.execute(
            "INSERT INTO shop_transactions (user_id, item_id, price_coins) VALUES ($1,$2,$3)",
            user_id,
            item_id,
            int(item["price_coins"]),
        )
        inv = await conn.fetchrow(
            "SELECT quantity FROM user_inventory WHERE user_id=$1 AND item_id=$2 FOR UPDATE",
            user_id,
            item_id,
        )
        if inv:
            quantity = int(inv["quantity"]) + 1
            await conn.execute(
                "UPDATE user_inventory SET quantity=$3 WHERE user_id=$1 AND item_id=$2",
                user_id,
                item_id,
                quantity,
            )
        else:
            quantity = 1
            await conn.execute(
                "INSERT INTO user_inventory (user_id, item_id, quantity) VALUES ($1,$2,1)",
                user_id,
                item_id,
            )
    return {"ok": True, "item_id": item_id, "quantity": quantity}


@app.get("/api/v1/promotions/feed")
async def promotion_feed(request: Request, user_id: int = Depends(current_user_id)):
    db = db_from_request(request)
    async with db.transaction() as conn:
        campaign = None
        campaigns = await conn.fetch(
            """
            SELECT pc.id, pc.entity_id, pc.impressions_total, pc.impressions_used,
                   e.title, e.username, e.telegram_chat_id
            FROM promotion_campaigns pc
            JOIN entities e ON e.id=pc.entity_id
            WHERE pc.status='active' AND e.is_active=TRUE
              AND pc.impressions_used < pc.impressions_total
            ORDER BY pc.started_at NULLS LAST, pc.created_at, pc.id
            LIMIT 25
            """
        )
        for candidate in campaigns:
            try:
                inserted = await conn.execute(
                    """
                    INSERT INTO promotion_impressions (campaign_id, telegram_id)
                    VALUES ($1, $2)
                    ON CONFLICT (campaign_id, telegram_id) DO NOTHING
                    """,
                    candidate["id"],
                    user_id,
                )
                if inserted == "INSERT 0 0":
                    continue
                updated = await conn.fetchrow(
                    """
                    UPDATE promotion_campaigns
                    SET impressions_used=impressions_used+1,
                        status=CASE WHEN impressions_used+1 >= impressions_total THEN 'finished' ELSE status END,
                        finished_at=CASE WHEN impressions_used+1 >= impressions_total THEN NOW() ELSE finished_at END
                    WHERE id=$1 AND status='active' AND impressions_used < impressions_total
                    RETURNING id
                    """,
                    candidate["id"],
                )
                if updated:
                    campaign = candidate
                    break
                await conn.execute(
                    "DELETE FROM promotion_impressions WHERE campaign_id=$1 AND telegram_id=$2",
                    candidate["id"],
                    user_id,
                )
            except Exception:
                continue
    if not campaign:
        return {"campaign": None}
    return {
        "campaign": {
            "id": str(campaign["id"]),
            "title": campaign["title"],
            "username": campaign["username"],
            "url": f"https://t.me/{str(campaign['username']).lstrip('@')}",
        }
    }


@app.post("/api/v1/promotions/{campaign_id}/click")
async def promotion_click(campaign_id: uuid.UUID, request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).transaction() as conn:
        result = await conn.fetchrow(
            """
            UPDATE promotion_campaigns
            SET clicks_total=clicks_total+1
            WHERE id=$1 AND status IN ('active','finished')
            RETURNING id
            """,
            campaign_id,
        )
        if not result:
            raise HTTPException(404, "Campaign not found")
        await conn.execute(
            "INSERT INTO promotion_clicks (campaign_id, telegram_id) VALUES ($1,$2)",
            campaign_id,
            user_id,
        )
    return {"ok": True}


@app.post("/api/v1/game/start")
async def start_game(request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).transaction() as conn:
        await ensure_user(conn, user_id)
        _, questions, engine = await load_game_data(conn)
        question_ids = [int(q["id"]) for q in questions]
        qid = engine.choose_question(question_ids)
        session_id = uuid.uuid4()
        await conn.execute(
            """
            INSERT INTO game_sessions (id, telegram_id, status, question_count, engine_state)
            VALUES ($1,$2,'active',0,$3::jsonb)
            """,
            session_id,
            user_id,
            json.dumps({"posterior": {str(k): v for k, v in engine.posterior.items()}, "used_questions": [qid]}),
        )
        await conn.execute(
            "UPDATE users SET games_played=games_played+1, updated_at=NOW() WHERE telegram_id=$1",
            user_id,
        )
        question = next(q for q in questions if int(q["id"]) == qid)
    return {
        "session_id": str(session_id),
        "question": {"id": qid, "text": question["text"]},
        "question_number": 1,
        "total_questions": len(question_ids),
    }


@app.post("/api/v1/game/{session_id}/answer")
async def answer_game(session_id: uuid.UUID, payload: AnswerRequest, request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).transaction() as conn:
        session = await conn.fetchrow(
            "SELECT * FROM game_sessions WHERE id=$1 AND telegram_id=$2 FOR UPDATE",
            session_id,
            user_id,
        )
        if not session or session["status"] != "active":
            raise HTTPException(404, "Session not found")
        _, questions, engine = await load_game_data(conn)
        state = dict(session["engine_state"] or {})
        try:
            engine.posterior = {int(k): float(v) for k, v in dict(state.get("posterior", {})).items()}
            used = [int(x) for x in state.get("used_questions", [])]
        except (TypeError, ValueError):
            raise HTTPException(409, "Invalid game state")
        if not used or payload.question_id != used[-1]:
            raise HTTPException(400, "Question does not belong to the current turn")
        if not await conn.fetchval(
            "SELECT 1 FROM questions WHERE id=$1 AND is_active=TRUE",
            payload.question_id,
        ):
            raise HTTPException(400, "Unknown question")

        new_count = int(session["question_count"]) + 1
        await conn.execute(
            "INSERT INTO game_answers (session_id, question_id, answer_value, question_number) VALUES ($1,$2,$3,$4)",
            session_id,
            payload.question_id,
            payload.answer,
            new_count,
        )
        engine.answer(payload.question_id, payload.answer)
        guessed_id, confidence, posterior = engine.best()
        question_ids = [int(q["id"]) for q in questions]

        if new_count >= MAX_QUESTIONS or len(used) >= len(question_ids):
            status = "won" if guessed_id is not None else "lost"
            await conn.execute(
                """
                UPDATE game_sessions
                SET question_count=$2, guessed_entity_id=$3, status=$4, finished_at=NOW(), engine_state=$5::jsonb
                WHERE id=$1
                """,
                session_id,
                new_count,
                guessed_id,
                status,
                json.dumps({"posterior": {str(k): v for k, v in posterior.items()}, "used_questions": used}),
            )
            if status == "won":
                await conn.execute(
                    "UPDATE users SET games_won=games_won+1, coins_available=coins_available+20, updated_at=NOW() WHERE telegram_id=$1",
                    user_id,
                )
                await conn.execute(
                    """
                    INSERT INTO coin_transactions (user_id, amount, type, reference_id, status)
                    SELECT $1, 20, 'game_win', $2, 'completed'
                    WHERE NOT EXISTS (
                        SELECT 1 FROM coin_transactions WHERE user_id=$1 AND type='game_win' AND reference_id=$2
                    )
                    """,
                    user_id,
                    str(session_id),
                )
            return {"finished": True, "result": status, "entity_id": guessed_id, "confidence": confidence}

        remaining = [qid for qid in question_ids if qid not in used]
        if not remaining:
            raise HTTPException(503, "No next question available")
        next_qid = engine.choose_question(remaining)
        used.append(next_qid)
        await conn.execute(
            "UPDATE game_sessions SET question_count=$2, engine_state=$3::jsonb WHERE id=$1",
            session_id,
            new_count,
            json.dumps({"posterior": {str(k): v for k, v in posterior.items()}, "used_questions": used}),
        )
        question = next(q for q in questions if int(q["id"]) == next_qid)
    return {
        "finished": False,
        "question_number": new_count + 1,
        "total_questions": len(question_ids),
        "question": {"id": next_qid, "text": question["text"]},
        "session_id": str(session_id),
    }


@app.get("/api/v1/game/{session_id}/result")
async def game_result(session_id: uuid.UUID, request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).connection() as conn:
        session = await conn.fetchrow(
            "SELECT status, guessed_entity_id, engine_state FROM game_sessions WHERE id=$1 AND telegram_id=$2",
            session_id,
            user_id,
        )
        if not session:
            raise HTTPException(404, "Session not found")
        entity = (
            await conn.fetchrow(
                "SELECT id, title, username, entity_type FROM entities WHERE id=$1",
                session["guessed_entity_id"],
            )
            if session["guessed_entity_id"]
            else None
        )
        posterior = dict((session["engine_state"] or {}).get("posterior", {}))
        confidence = float(posterior.get(str(session["guessed_entity_id"]), 0.0)) if entity else 0.0
    return {"status": session["status"], "entity": dict(entity) if entity else None, "confidence": confidence}


@app.get("/api/v1/tasks")
async def tasks(request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).connection() as conn:
        rows = await conn.fetch(
            """
            SELECT t.id, t.title, t.description, t.reward_coins, t.hold_hours, t.channel_username,
                   CASE WHEN ut.status IN ('on_hold','rewarded') THEN TRUE ELSE FALSE END AS already_started,
                   ut.status AS user_status
            FROM tasks t
            LEFT JOIN user_tasks ut ON ut.task_id=t.id AND ut.user_id=$1
            WHERE t.is_active=TRUE
            ORDER BY t.id
            """,
            user_id,
        )
    return [dict(r) for r in rows]


@app.post("/api/v1/tasks/{task_id}/verify")
async def verify_task(task_id: int, request: Request, user_id: int = Depends(current_user_id)):
    env = request.scope["env"]
    cfgv = Config.from_env(env)
    db = db_from_request(request)

    async with db.connection() as conn:
        task = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 AND is_active=TRUE", task_id)
        row = await conn.fetchrow(
            "SELECT status FROM user_tasks WHERE user_id=$1 AND task_id=$2",
            user_id,
            task_id,
        )
    if not task or task["task_type"] != "subscription" or not task["channel_id"]:
        raise HTTPException(404, "Task not found")
    if row and row["status"] in {"rewarded", "on_hold"}:
        return {"verified": row["status"] == "rewarded", "status": row["status"]}

    try:
        member = await get_chat_member(env, int(task["channel_id"]), user_id)
    except TelegramError:
        return {"verified": False, "status": "telegram_error"}
    if not member_is_subscribed(member):
        return {"verified": False, "status": "not_subscribed"}

    now = datetime.now(timezone.utc)
    hold_hours = int(task["hold_hours"] or cfgv.task_hold_hours)
    hold_until = now + timedelta(hours=hold_hours)

    async with db.transaction() as conn:
        task_locked = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 AND is_active=TRUE FOR UPDATE", task_id)
        if not task_locked or not task_locked["channel_id"]:
            raise HTTPException(404, "Task not found")
        current = await conn.fetchrow(
            "SELECT status FROM user_tasks WHERE user_id=$1 AND task_id=$2 FOR UPDATE",
            user_id,
            task_id,
        )
        if current and current["status"] in {"rewarded", "on_hold"}:
            return {"verified": current["status"] == "rewarded", "status": current["status"]}
        await ensure_user(conn, user_id)
        if not current:
            await conn.execute(
                """
                INSERT INTO user_tasks (user_id, task_id, status, started_at, completed_at, hold_until)
                VALUES ($1,$2,'on_hold',$3,$3,$4)
                """,
                user_id,
                task_id,
                now,
                hold_until,
            )
        else:
            await conn.execute(
                "UPDATE user_tasks SET status='on_hold', completed_at=$3, hold_until=$4 WHERE user_id=$1 AND task_id=$2",
                user_id,
                task_id,
                now,
                hold_until,
            )
        await conn.execute(
            "INSERT INTO coin_transactions (user_id, amount, type, reference_id, status) VALUES ($1,$2,'task_hold',$3,'hold')",
            user_id,
            int(task_locked["reward_coins"]),
            str(task_id),
        )
        await conn.execute(
            "UPDATE users SET coins_hold=coins_hold+$2, updated_at=NOW() WHERE telegram_id=$1",
            user_id,
            int(task_locked["reward_coins"]),
        )
    return {"verified": True, "status": "on_hold", "hold_hours": hold_hours}


@app.get("/api/v1/entities/mine")
async def my_entities(request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).connection() as conn:
        rows = await conn.fetch(
            """
            SELECT e.id, e.title, e.username, e.is_active, e.is_promoted,
                   COALESCE(o.verified,FALSE) AS ownership_verified,
                   COALESCE(pc.impressions_total,0) AS impressions_total,
                   COALESCE(pc.impressions_used,0) AS impressions_used,
                   COALESCE(pc.clicks_total,0) AS clicks_total,
                   COALESCE(pc.status,'none') AS promotion_status
            FROM entities e
            LEFT JOIN channel_ownerships o ON o.entity_id=e.id AND o.telegram_id=$1
            LEFT JOIN LATERAL (
              SELECT * FROM promotion_campaigns pc2 WHERE pc2.entity_id=e.id AND pc2.owner_telegram_id=$1 ORDER BY pc2.created_at DESC LIMIT 1
            ) pc ON TRUE
            WHERE e.owner_telegram_id=$1
            ORDER BY e.created_at DESC
            """,
            user_id,
        )
    return [dict(r) for r in rows]


@app.post("/api/v1/entities/propose")
async def propose_entity(payload: ProposeEntity, request: Request, user_id: int = Depends(current_user_id)):
    env = request.scope["env"]
    username = normalize_public_username(payload.username)
    try:
        chat = await get_chat(env, username)
        if chat.get("type") != "channel":
            raise HTTPException(400, "Это не Telegram-канал")
        bot = await get_me(env)
        bot_member = await get_chat_member(env, int(chat["id"]), int(bot["id"]))
        owner_member = await get_chat_member(env, int(chat["id"]), user_id)
    except HTTPException:
        raise
    except TelegramError as exc:
        raise HTTPException(400, f"Telegram не дал проверить канал: {exc}") from exc

    if not member_is_owner(bot_member):
        raise HTTPException(400, "Сначала добавьте бота администратором канала")
    if not member_is_owner(owner_member):
        raise HTTPException(403, "Вы должны быть администратором канала")

    db = db_from_request(request)
    async with db.transaction() as conn:
        await ensure_user(conn, user_id)
        exists = await conn.fetchval(
            "SELECT 1 FROM entities WHERE username=$1 OR telegram_chat_id=$2",
            username,
            int(chat["id"]),
        )
        pending = await conn.fetchval(
            "SELECT 1 FROM pending_entities WHERE username=$1 AND status='pending'",
            username,
        )
        if exists or pending:
            raise HTTPException(409, "Этот канал уже есть или уже отправлен на модерацию")
        row = await conn.fetchrow(
            """
            INSERT INTO pending_entities (author_telegram_id, title, username, telegram_chat_id, ownership_verified, status)
            VALUES ($1,$2,$3,$4,TRUE,'pending')
            RETURNING id, status
            """,
            user_id,
            payload.title.strip(),
            username,
            int(chat["id"]),
        )
    return {"id": int(row["id"]), "status": row["status"], "ownership_verified": True}


@app.post("/api/v1/entities/{entity_id}/reverify")
async def reverify_entity(entity_id: int, request: Request, user_id: int = Depends(current_user_id)):
    env = request.scope["env"]
    db = db_from_request(request)
    async with db.connection() as conn:
        entity = await conn.fetchrow(
            "SELECT * FROM entities WHERE id=$1 AND owner_telegram_id=$2",
            entity_id,
            user_id,
        )
    if not entity:
        raise HTTPException(404, "Channel not found")
    if not entity["telegram_chat_id"]:
        raise HTTPException(409, "Channel has no Telegram chat id")
    try:
        member = await get_chat_member(env, int(entity["telegram_chat_id"]), user_id)
        ok = member_is_owner(member)
    except TelegramError:
        ok = False

    async with db.transaction() as conn:
        current = await conn.fetchrow(
            "SELECT verified FROM channel_ownerships WHERE entity_id=$1 AND telegram_id=$2 FOR UPDATE",
            entity_id,
            user_id,
        )
        if not current:
            await conn.execute(
                """
                INSERT INTO channel_ownerships (entity_id, telegram_id, verification_method, verified, verified_at)
                VALUES ($1,$2,'admin',$3,CASE WHEN $3 THEN NOW() ELSE NULL END)
                """,
                entity_id,
                user_id,
                ok,
            )
        else:
            await conn.execute(
                "UPDATE channel_ownerships SET verified=$3, verified_at=CASE WHEN $3 THEN NOW() ELSE NULL END WHERE entity_id=$1 AND telegram_id=$2",
                entity_id,
                user_id,
                ok,
            )
        if not ok:
            await conn.execute("UPDATE entities SET is_active=FALSE, is_promoted=FALSE WHERE id=$1", entity_id)
            await conn.execute(
                "UPDATE promotion_campaigns SET status='paused' WHERE entity_id=$1 AND status='active'",
                entity_id,
            )
    return {"verified": ok}


@app.post("/api/v1/entities/{entity_id}/report")
async def report_entity(entity_id: int, payload: EntityReport, request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).transaction() as conn:
        exists = await conn.fetchval("SELECT 1 FROM entities WHERE id=$1 AND is_active=TRUE", entity_id)
        if not exists:
            raise HTTPException(404, "Channel not found")
        await ensure_user(conn, user_id)
        inserted = await conn.execute(
            """
            INSERT INTO entity_reports (entity_id, telegram_id, reason)
            VALUES ($1,$2,$3)
            ON CONFLICT (entity_id, telegram_id) DO NOTHING
            """,
            entity_id,
            user_id,
            payload.reason.strip() if payload.reason else None,
        )
        if inserted == "INSERT 0 0":
            raise HTTPException(409, "Вы уже пожаловались на этот канал")
        await conn.execute("UPDATE entities SET reports_count=reports_count+1, updated_at=NOW() WHERE id=$1", entity_id)
    return {"ok": True}


@app.post("/api/v1/promotions")
async def create_promotion(payload: CreatePromotion, request: Request, user_id: int = Depends(current_user_id)):
    env = request.scope["env"]
    cfgv = Config.from_env(env)
    if not cfgv.payment_provider_token:
        raise HTTPException(503, "Платежи не настроены: добавьте PAYMENT_PROVIDER_TOKEN")

    db = db_from_request(request)
    campaign_id = uuid.uuid4()
    payment_id = uuid.uuid4()
    invoice_payload = f"tg_jinni:campaign:{campaign_id}"
    async with db.transaction() as conn:
        entity = await conn.fetchrow(
            """
            SELECT e.id, e.title, e.username
            FROM entities e
            JOIN channel_ownerships o ON o.entity_id=e.id AND o.telegram_id=$2 AND o.verified=TRUE
            WHERE e.id=$1 AND e.owner_telegram_id=$2 AND e.is_active=TRUE
            """,
            payload.entity_id,
            user_id,
        )
        if not entity:
            raise HTTPException(403, "Сначала подтвердите владение каналом")
        await ensure_user(conn, user_id)
        await conn.execute(
            """
            INSERT INTO promotion_campaigns (id, entity_id, owner_telegram_id, impressions_total, impressions_used, clicks_total, price_rub, status)
            VALUES ($1,$2,$3,$4,0,0,$5,'pending_payment')
            """,
            campaign_id,
            entity["id"],
            user_id,
            cfgv.promotion_impressions,
            cfgv.promotion_price_rub,
        )
        await conn.execute(
            """
            INSERT INTO payments (id, telegram_id, campaign_id, amount, currency, status, invoice_payload)
            VALUES ($1,$2,$3,$4,'RUB','pending',$5)
            """,
            payment_id,
            user_id,
            campaign_id,
            cfgv.promotion_price_rub,
            invoice_payload,
        )

    try:
        invoice_link = await create_invoice_link(
            env,
            title=f"Продвижение: {entity['title']}",
            description=f"{cfgv.promotion_impressions} показов кнопки подписки",
            payload=invoice_payload,
            amount_rub=cfgv.promotion_price_rub,
        )
    except TelegramError as exc:
        async with db.transaction() as conn:
            await conn.execute("DELETE FROM payments WHERE id=$1", payment_id)
            await conn.execute("DELETE FROM promotion_campaigns WHERE id=$1", campaign_id)
        raise HTTPException(502, f"Не удалось создать счёт: {exc}") from exc

    return {
        "campaign_id": str(campaign_id),
        "payment_id": str(payment_id),
        "price_rub": cfgv.promotion_price_rub,
        "impressions": cfgv.promotion_impressions,
        "invoice_url": invoice_link,
    }


@app.get("/api/v1/promotions/{campaign_id}/stats")
async def promotion_stats(campaign_id: uuid.UUID, request: Request, user_id: int = Depends(current_user_id)):
    async with db_from_request(request).connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT pc.status, pc.impressions_total, pc.impressions_used, pc.clicks_total, pc.price_rub,
                   p.status AS payment_status
            FROM promotion_campaigns pc
            JOIN payments p ON p.campaign_id=pc.id
            WHERE pc.id=$1 AND pc.owner_telegram_id=$2
            ORDER BY p.created_at DESC LIMIT 1
            """,
            campaign_id,
            user_id,
        )
        if not row:
            raise HTTPException(404, "Campaign not found")
    used = int(row["impressions_used"])
    clicks = int(row["clicks_total"])
    ctr = round(clicks / used * 100, 2) if used else 0.0
    return {
        **dict(row),
        "impressions_remaining": max(0, int(row["impressions_total"]) - used),
        "ctr": ctr,
    }


@app.get("/api/v1/admin/pending")
async def admin_pending(request: Request, _admin_id: int = Depends(admin_required)):
    async with db_from_request(request).connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, author_telegram_id, title, username, telegram_chat_id,
                   ownership_verified, status, moderator_comment, created_at
            FROM pending_entities
            WHERE status='pending'
            ORDER BY created_at ASC
            """
        )
    return [dict(r) for r in rows]


@app.post("/api/v1/admin/pending/{pending_id}/approve")
async def admin_approve(
    pending_id: int,
    request: Request,
    body: ModerationComment,
    admin_id: int = Depends(admin_required),
):
    db = db_from_request(request)
    async with db.transaction() as conn:
        pending = await conn.fetchrow(
            "SELECT * FROM pending_entities WHERE id=$1 AND status='pending' FOR UPDATE",
            pending_id,
        )
        if not pending:
            raise HTTPException(404, "Pending entity not found")
        exists = await conn.fetchrow(
            "SELECT id FROM entities WHERE username=$1 OR telegram_chat_id=$2",
            pending["username"],
            pending["telegram_chat_id"],
        )
        if exists:
            await conn.execute(
                "UPDATE pending_entities SET status='rejected', moderator_telegram_id=$2, moderator_comment='Duplicate entity', reviewed_at=NOW() WHERE id=$1",
                pending_id,
                admin_id,
            )
            raise HTTPException(409, "Entity already exists")
        await ensure_user(conn, int(pending["author_telegram_id"]))
        entity = await conn.fetchrow(
            """
            INSERT INTO entities (title, username, telegram_chat_id, entity_type, owner_telegram_id, is_active, is_promoted)
            VALUES ($1,$2,$3,'channel',$4,TRUE,FALSE)
            RETURNING id
            """,
            pending["title"],
            pending["username"],
            pending["telegram_chat_id"],
            pending["author_telegram_id"],
        )
        await conn.execute(
            """
            INSERT INTO channel_ownerships (entity_id, telegram_id, verification_method, verified, verified_at)
            VALUES ($1,$2,'admin',TRUE,NOW())
            ON CONFLICT DO NOTHING
            """,
            entity["id"],
            pending["author_telegram_id"],
        )
        await conn.execute(
            "UPDATE pending_entities SET status='approved', moderator_telegram_id=$2, moderator_comment=$3, reviewed_at=NOW() WHERE id=$1",
            pending_id,
            admin_id,
            body.comment,
        )
        author_id = int(pending["author_telegram_id"])
    try:
        await send_message(request.scope["env"], author_id, "✅ Канал одобрен и добавлен в TG-Jinni.")
    except TelegramError:
        pass
    return {"ok": True, "entity_id": int(entity["id"])}


@app.post("/api/v1/admin/pending/{pending_id}/reject")
async def admin_reject(
    pending_id: int,
    request: Request,
    body: ModerationComment,
    admin_id: int = Depends(admin_required),
):
    db = db_from_request(request)
    async with db.transaction() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM pending_entities WHERE id=$1 AND status='pending' FOR UPDATE",
            pending_id,
        )
        if not row:
            raise HTTPException(404, "Pending entity not found")
        await conn.execute(
            "UPDATE pending_entities SET status='rejected', moderator_telegram_id=$2, moderator_comment=$3, reviewed_at=NOW() WHERE id=$1",
            pending_id,
            admin_id,
            body.comment,
        )
        author_id = int(row["author_telegram_id"])
    try:
        comment = f"\nПричина: {body.comment}" if body.comment else ""
        await send_message(request.scope["env"], author_id, "❌ Заявка на канал отклонена." + comment)
    except TelegramError:
        pass
    return {"ok": True}


@app.get("/api/v1/admin/stats")
async def admin_stats(request: Request, _admin_id: int = Depends(admin_required)):
    async with db_from_request(request).connection() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM users")
        channels = await conn.fetchval("SELECT COUNT(*) FROM entities WHERE entity_type='channel'")
        pending = await conn.fetchval("SELECT COUNT(*) FROM pending_entities WHERE status='pending'")
        active_campaigns = await conn.fetchval("SELECT COUNT(*) FROM promotion_campaigns WHERE status='active'")
        payments_paid = await conn.fetchval("SELECT COUNT(*) FROM payments WHERE status='paid'")
        reports = await conn.fetchval("SELECT COUNT(*) FROM entity_reports")
    return {
        "users": int(users),
        "channels": int(channels),
        "pending_channels": int(pending),
        "active_campaigns": int(active_campaigns),
        "paid_payments": int(payments_paid),
        "reports": int(reports),
    }


async def run_maintenance(env) -> None:
    cfgv = Config.from_env(env)
    db = Database(env)

    # Keep Telegram calls OUTSIDE DB transactions. This prevents a slow Bot API call
    # from holding PostgreSQL locks/connections for the whole Cron invocation.
    async with db.connection() as conn:
        holds = await conn.fetch(
            """
            SELECT ut.user_id, ut.task_id, t.reward_coins, t.channel_id
            FROM user_tasks ut
            JOIN tasks t ON t.id=ut.task_id
            WHERE ut.status='on_hold' AND ut.hold_until IS NOT NULL AND ut.hold_until <= NOW()
            ORDER BY ut.hold_until
            LIMIT 50
            """
        )

    for row in holds:
        try:
            member = await get_chat_member(env, int(row["channel_id"]), int(row["user_id"])) if row["channel_id"] else None
            ok = bool(member and member_is_subscribed(member))
        except TelegramError:
            ok = False

        async with db.transaction() as conn:
            current = await conn.fetchrow(
                "SELECT status, hold_until FROM user_tasks WHERE user_id=$1 AND task_id=$2 FOR UPDATE",
                row["user_id"],
                row["task_id"],
            )
            if not current or current["status"] != "on_hold" or not current["hold_until"]:
                continue
            if current["hold_until"] > datetime.now(timezone.utc):
                continue

            user = await conn.fetchrow(
                "SELECT coins_hold FROM users WHERE telegram_id=$1 FOR UPDATE",
                row["user_id"],
            )
            if not user:
                continue
            amount = int(row["reward_coins"])
            release_ok = ok and int(user["coins_hold"]) >= amount
            if release_ok:
                await conn.execute(
                    "UPDATE users SET coins_hold=coins_hold-$2, coins_available=coins_available+$2, updated_at=NOW() WHERE telegram_id=$1",
                    row["user_id"],
                    amount,
                )
                await conn.execute(
                    "UPDATE user_tasks SET status='rewarded', rewarded_at=NOW() WHERE user_id=$1 AND task_id=$2",
                    row["user_id"],
                    row["task_id"],
                )
                await conn.execute(
                    "UPDATE coin_transactions SET status='completed' WHERE user_id=$1 AND type='task_hold' AND reference_id=$2 AND status='hold'",
                    row["user_id"],
                    str(row["task_id"]),
                )
            else:
                await conn.execute(
                    "UPDATE users SET coins_hold=GREATEST(coins_hold-$2,0), updated_at=NOW() WHERE telegram_id=$1",
                    row["user_id"],
                    amount,
                )
                await conn.execute(
                    "UPDATE user_tasks SET status='cancelled' WHERE user_id=$1 AND task_id=$2",
                    row["user_id"],
                    row["task_id"],
                )
                await conn.execute(
                    "UPDATE coin_transactions SET status='cancelled' WHERE user_id=$1 AND type='task_hold' AND reference_id=$2 AND status='hold'",
                    row["user_id"],
                    str(row["task_id"]),
                )

    async with db.connection() as conn:
        channels = await conn.fetch(
            """
            SELECT e.id, e.owner_telegram_id, e.telegram_chat_id
            FROM entities e
            JOIN channel_ownerships o ON o.entity_id=e.id AND o.verified=TRUE
            WHERE e.entity_type='channel' AND e.is_active=TRUE
              AND (o.verified_at IS NULL OR o.verified_at <= NOW() - ($1::text || ' hours')::interval)
            ORDER BY o.verified_at NULLS FIRST
            LIMIT 25
            """,
            int(cfgv.ownership_recheck_hours),
        )

    for row in channels:
        try:
            member = await get_chat_member(env, int(row["telegram_chat_id"]), int(row["owner_telegram_id"]))
            ok = member_is_owner(member)
        except TelegramError:
            ok = False

        async with db.transaction() as conn:
            ownership = await conn.fetchrow(
                "SELECT verified FROM channel_ownerships WHERE entity_id=$1 AND telegram_id=$2 FOR UPDATE",
                row["id"],
                row["owner_telegram_id"],
            )
            if not ownership or not ownership["verified"]:
                continue
            await conn.execute(
                "UPDATE channel_ownerships SET verified=$3, verified_at=CASE WHEN $3 THEN NOW() ELSE NOW() END WHERE entity_id=$1 AND telegram_id=$2",
                row["id"],
                row["owner_telegram_id"],
                ok,
            )
            if not ok:
                await conn.execute(
                    "UPDATE entities SET is_active=FALSE, is_promoted=FALSE, updated_at=NOW() WHERE id=$1",
                    row["id"],
                )
                await conn.execute(
                    "UPDATE promotion_campaigns SET status='paused' WHERE entity_id=$1 AND status='active'",
                    row["id"],
                )


def hmac_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        if request.method == "POST" and str(request.url).split("?", 1)[0].endswith("/telegram/webhook"):
            env = self.env
            expected = Config.from_env(env).require_webhook_secret()
            supplied = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac_compare(supplied, expected):
                return Response("Unauthorized", status=401)
            update = await request.json()
            base_url = str(request.url).split("/telegram/webhook", 1)[0]
            await handle_update(env, update, base_url)
            return Response("OK", status=200)
        return await asgi.fetch(app, request, self.env)

    async def scheduled(self, controller, env, ctx):
        if controller.cron == "17 * * * *":
            await run_maintenance(env)


@app.get("/", include_in_schema=False)
async def root(request: Request):
    return await serve_asset(request)


@app.get("/{path:path}", include_in_schema=False)
async def frontend(path: str, request: Request):
    return await serve_asset(request, path)

from datetime import datetime, timezone

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, current_user_id
from app.config.settings import get_settings
from app.database.models import ChannelOwnership, Entity, PendingEntity
from app.schemas.api import ProposeEntity
from app.telegram.client import get_public_channel, check_admin, check_bot_admin

router = APIRouter(prefix="/entities", tags=["entities"])
settings = get_settings()


def normalize_username(value: str) -> str:
    value = value.strip()
    if value.startswith("https://t.me/"):
        value = "@" + value.rstrip("/").split("/")[-1]
    if not value.startswith("@"):
        value = "@" + value
    return value


@router.post("/propose")
async def propose(payload: ProposeEntity, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    username = normalize_username(payload.username)
    bot = Bot(settings.bot_token)
    try:
        chat = await get_public_channel(bot, username)
        if chat.type != "channel":
            raise HTTPException(400, "The supplied Telegram chat is not a channel")
        if not await check_bot_admin(bot, chat.id):
            raise HTTPException(400, "Add the bot as an administrator of the channel first")
        if not await check_admin(bot, chat.id, user_id):
            raise HTTPException(403, "You must be an administrator of the channel")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(400, "Channel is unavailable or the bot cannot verify ownership")
    finally:
        await bot.session.close()

    exists = await db.execute(select(Entity).where((Entity.username == username) | (Entity.telegram_chat_id == chat.id)))
    if exists.scalar_one_or_none():
        raise HTTPException(409, "Channel already exists")
    pending = PendingEntity(
        author_telegram_id=user_id,
        title=payload.title.strip(),
        username=username,
        telegram_chat_id=chat.id,
        ownership_verified=True,
    )
    db.add(pending)
    await db.commit()
    return {"id": pending.id, "status": pending.status, "ownership_verified": True}


@router.get("/mine")
async def my_channels(user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    rows = (await db.execute(select(Entity).where(Entity.owner_telegram_id == user_id).order_by(Entity.created_at.desc()))).scalars()
    return [{"id": e.id, "title": e.title, "username": e.username, "is_active": e.is_active, "is_promoted": e.is_promoted} for e in rows]


@router.post("/{entity_id}/verify")
async def verify(entity_id: int, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    entity = await db.get(Entity, entity_id)
    if not entity or entity.entity_type != "channel" or not entity.telegram_chat_id:
        raise HTTPException(404, "Channel not found")
    bot = Bot(settings.bot_token)
    try:
        ok = await check_admin(bot, entity.telegram_chat_id, user_id)
    except Exception:
        ok = False
    finally:
        await bot.session.close()
    ownership = await db.execute(select(ChannelOwnership).where(ChannelOwnership.entity_id == entity_id, ChannelOwnership.telegram_id == user_id))
    row = ownership.scalar_one_or_none()
    if not row:
        row = ChannelOwnership(entity_id=entity_id, telegram_id=user_id, verification_method="admin")
        db.add(row)
    row.verified = ok
    row.verified_at = datetime.now(timezone.utc) if ok else None
    if ok:
        entity.owner_telegram_id = user_id
    await db.commit()
    return {"verified": ok}

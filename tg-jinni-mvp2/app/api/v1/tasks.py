from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from app.api.deps import db_session, current_user_id
from app.config.settings import get_settings
from app.database.models import Task
from app.tasks.service import verify_subscription

router = APIRouter(prefix='/tasks', tags=['tasks'])
settings = get_settings()

@router.get('')
async def list_tasks(db: AsyncSession = Depends(db_session)):
    rows = (await db.execute(select(Task).where(Task.is_active.is_(True)).order_by(Task.id))).scalars()
    return [{'id': t.id, 'title': t.title, 'description': t.description, 'reward_coins': t.reward_coins, 'channel_username': t.channel_username} for t in rows]

@router.post('/{task_id}/verify')
async def verify_task(task_id: int, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    bot = Bot(settings.bot_token)
    try:
        ok = await verify_subscription(db, bot, user_id, task_id)
    except Exception:
        ok = False
    finally:
        await bot.session.close()
    await db.commit()
    return {'verified': ok}

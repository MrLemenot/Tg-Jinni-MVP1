from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
from app.database.models import Task, UserTask
from app.telegram.client import check_member
from app.economy.wallet import hold_coins, release_hold, cancel_hold

async def verify_subscription(db: AsyncSession, bot: Bot, user_id: int, task_id: int) -> bool:
    task = await db.get(Task, task_id)
    if not task or not task.is_active or task.task_type != 'subscription' or not task.channel_id:
        return False
    row = await db.get(UserTask, {'user_id': user_id, 'task_id': task_id})
    if not row:
        row = UserTask(user_id=user_id, task_id=task_id, status='started', started_at=datetime.now(timezone.utc))
        db.add(row)
        await db.flush()
    if row.status in {'on_hold', 'rewarded', 'cancelled'}:
        return row.status == 'rewarded'
    if not await check_member(bot, task.channel_id, user_id):
        return False
    now = datetime.now(timezone.utc)
    row.status = 'on_hold'
    row.completed_at = now
    row.hold_until = now + timedelta(hours=task.hold_hours)
    await hold_coins(db, user_id, task.reward_coins, str(task.id))
    return True


async def finalize_holds(db: AsyncSession, bot: Bot):
    now = datetime.now(timezone.utc)
    rows = list((await db.execute(select(UserTask, Task).join(Task, Task.id == UserTask.task_id).where(UserTask.status == 'on_hold', UserTask.hold_until <= now))).all())
    for row, task in rows:
        ok = bool(task.channel_id) and await check_member(bot, task.channel_id, row.user_id)
        if ok:
            await release_hold(db, row.user_id, task.reward_coins, str(task.id))
            row.status = 'rewarded'
            row.rewarded_at = now
        else:
            await cancel_hold(db, row.user_id, task.reward_coins, str(task.id))
            row.status = 'cancelled'
    await db.commit()

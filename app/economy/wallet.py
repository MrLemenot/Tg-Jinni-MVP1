from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import User, CoinTransaction

async def ensure_user(db: AsyncSession, telegram_id: int, username: str | None, first_name: str | None) -> User:
    user = await db.get(User, telegram_id)
    if not user:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        db.add(user)
    else:
        user.username, user.first_name = username, first_name
    await db.flush()
    return user

async def add_coins(db: AsyncSession, user_id: int, amount: int, tx_type: str, reference_id: str | None = None) -> None:
    user = await db.get(User, user_id, with_for_update=True)
    if not user:
        raise ValueError('User not found')
    user.coins_available += amount
    db.add(CoinTransaction(user_id=user_id, amount=amount, type=tx_type, reference_id=reference_id))
    await db.flush()

async def spend_coins(db: AsyncSession, user_id: int, amount: int, tx_type: str, reference_id: str | None = None) -> None:
    user = await db.get(User, user_id, with_for_update=True)
    if not user or user.coins_available < amount:
        raise ValueError('Insufficient coins')
    user.coins_available -= amount
    db.add(CoinTransaction(user_id=user_id, amount=-amount, type=tx_type, reference_id=reference_id))
    await db.flush()


async def hold_coins(db: AsyncSession, user_id: int, amount: int, reference_id: str | None = None) -> None:
    user = await db.get(User, user_id, with_for_update=True)
    if not user:
        raise ValueError('User not found')
    user.coins_hold += amount
    db.add(CoinTransaction(user_id=user_id, amount=amount, type='hold', reference_id=reference_id, status='hold'))
    await db.flush()

async def release_hold(db: AsyncSession, user_id: int, amount: int, reference_id: str | None = None) -> None:
    user = await db.get(User, user_id, with_for_update=True)
    if not user or user.coins_hold < amount:
        raise ValueError('Invalid hold')
    user.coins_hold -= amount
    user.coins_available += amount
    db.add(CoinTransaction(user_id=user_id, amount=amount, type='hold_release', reference_id=reference_id))
    await db.flush()

async def cancel_hold(db: AsyncSession, user_id: int, amount: int, reference_id: str | None = None) -> None:
    user = await db.get(User, user_id, with_for_update=True)
    if not user or user.coins_hold < amount:
        raise ValueError('Invalid hold')
    user.coins_hold -= amount
    db.add(CoinTransaction(user_id=user_id, amount=-amount, type='hold_cancel', reference_id=reference_id, status='cancelled'))
    await db.flush()

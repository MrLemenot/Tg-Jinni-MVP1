from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, current_user_id
from app.database.models import ShopItem, UserInventory, ShopTransaction
from app.economy.wallet import spend_coins

router = APIRouter(prefix="/shop", tags=["shop"])


@router.get("")
async def shop(db: AsyncSession = Depends(db_session)):
    items = (await db.execute(select(ShopItem).where(ShopItem.is_active.is_(True)).order_by(ShopItem.id))).scalars()
    return [{"id": i.id, "title": i.title, "description": i.description, "item_type": i.item_type, "price_coins": i.price_coins} for i in items]


@router.post("/{item_id}/buy")
async def buy(item_id: int, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    item = await db.get(ShopItem, item_id)
    if not item or not item.is_active:
        raise HTTPException(404, "Item not found")
    try:
        await spend_coins(db, user_id, item.price_coins, "shop_purchase", str(item.id))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    inv = await db.get(UserInventory, {"user_id": user_id, "item_id": item.id})
    if not inv:
        inv = UserInventory(user_id=user_id, item_id=item.id, quantity=0)
        db.add(inv)
    inv.quantity += 1
    db.add(ShopTransaction(user_id=user_id, item_id=item.id, price_coins=item.price_coins))
    await db.commit()
    return {"ok": True, "item_id": item.id, "quantity": inv.quantity}

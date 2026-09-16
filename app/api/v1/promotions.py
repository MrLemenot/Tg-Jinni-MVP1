from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import db_session, current_user_id
from app.config.settings import get_settings
from app.database.models import ChannelOwnership, Entity, Payment, PromotionCampaign
from app.schemas.api import CreatePromotion
from app.economy.wallet import ensure_user

router = APIRouter(prefix='/promotions', tags=['promotions'])
settings = get_settings()

@router.post('')
async def create(payload: CreatePromotion, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    await ensure_user(db, user_id, None, None)
    entity = await db.get(Entity, payload.entity_id)
    ownership = (await db.execute(select(ChannelOwnership).where(ChannelOwnership.entity_id == payload.entity_id, ChannelOwnership.telegram_id == user_id, ChannelOwnership.verified.is_(True)))).scalar_one_or_none()
    if not entity or not ownership or not entity.is_active:
        raise HTTPException(403, 'Channel ownership must be verified')
    campaign = PromotionCampaign(entity_id=entity.id, owner_telegram_id=user_id, impressions_total=settings.promotion_package_impressions, price_rub=settings.promotion_package_price_rub)
    db.add(campaign)
    await db.flush()
    payment = Payment(telegram_id=user_id, campaign_id=campaign.id, amount=campaign.price_rub, currency='RUB', status='pending')
    db.add(payment)
    await db.commit()
    return {'campaign_id': str(campaign.id), 'payment_id': str(payment.id), 'price_rub': campaign.price_rub, 'impressions': campaign.impressions_total}

@router.post('/{campaign_id}/activate-demo')
async def activate_demo(campaign_id: str, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    campaign = await db.get(PromotionCampaign, campaign_id)
    if not campaign or campaign.owner_telegram_id != user_id:
        raise HTTPException(404, 'Campaign not found')
    campaign.status = 'active'; campaign.started_at = datetime.now(timezone.utc)
    await db.commit()
    return {'status': campaign.status}

@router.get('/{campaign_id}/stats')
async def stats(campaign_id: str, user_id: int = Depends(current_user_id), db: AsyncSession = Depends(db_session)):
    campaign = await db.get(PromotionCampaign, campaign_id)
    if not campaign or campaign.owner_telegram_id != user_id:
        raise HTTPException(404, 'Campaign not found')
    ctr = round(campaign.clicks_total / campaign.impressions_used * 100, 2) if campaign.impressions_used else 0
    return {'status': campaign.status, 'impressions_total': campaign.impressions_total, 'impressions_used': campaign.impressions_used, 'impressions_remaining': max(0, campaign.impressions_total - campaign.impressions_used), 'clicks': campaign.clicks_total, 'ctr': ctr}

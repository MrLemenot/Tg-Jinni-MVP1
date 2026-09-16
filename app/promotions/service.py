from datetime import datetime, timezone
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import PromotionCampaign, PromotionImpression, PromotionClick, Entity

async def reserve_impression(db: AsyncSession, user_id: int, game_session_id=None):
    q = select(PromotionCampaign).join(Entity, Entity.id == PromotionCampaign.entity_id).where(
        PromotionCampaign.status == 'active',
        PromotionCampaign.impressions_used < PromotionCampaign.impressions_total,
        Entity.is_active.is_(True)
    ).order_by(PromotionCampaign.created_at)
    campaigns = list((await db.execute(q)).scalars())
    for campaign in campaigns:
        result = await db.execute(update(PromotionCampaign).where(
            PromotionCampaign.id == campaign.id,
            PromotionCampaign.status == 'active',
            PromotionCampaign.impressions_used < PromotionCampaign.impressions_total
        ).values(impressions_used=PromotionCampaign.impressions_used + 1))
        if result.rowcount == 1:
            imp = PromotionImpression(campaign_id=campaign.id, telegram_id=user_id, game_session_id=game_session_id)
            db.add(imp)
            await db.flush()
            await db.refresh(campaign)
            if campaign.impressions_used >= campaign.impressions_total:
                campaign.status = 'finished'
                campaign.finished_at = datetime.now(timezone.utc)
            return campaign
    return None

async def register_click(db: AsyncSession, campaign_id, user_id: int):
    campaign = await db.get(PromotionCampaign, campaign_id, with_for_update=True)
    if not campaign:
        return False
    campaign.clicks_total += 1
    db.add(PromotionClick(campaign_id=campaign_id, telegram_id=user_id))
    await db.flush()
    return True

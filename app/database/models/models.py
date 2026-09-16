import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.database import Base

class User(Base):
    __tablename__ = 'users'
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    coins_available: Mapped[int] = mapped_column(BigInteger, default=0)
    coins_hold: Mapped[int] = mapped_column(BigInteger, default=0)
    games_played: Mapped[int] = mapped_column(Integer, default=0)
    games_won: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Entity(Base):
    __tablename__ = 'entities'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64), unique=True)
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    entity_type: Mapped[str] = mapped_column(String(32), default='channel')
    avatar_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    owner_telegram_id: Mapped[int | None] = mapped_column(ForeignKey('users.telegram_id'))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    reports_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ChannelOwnership(Base):
    __tablename__ = 'channel_ownerships'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey('entities.id', ondelete='CASCADE'))
    telegram_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id', ondelete='CASCADE'))
    verification_method: Mapped[str] = mapped_column(String(32))
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint('entity_id', 'telegram_id'),)

class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default='general')
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class EntityQuestionWeight(Base):
    __tablename__ = 'entity_question_weights'
    entity_id: Mapped[int] = mapped_column(ForeignKey('entities.id', ondelete='CASCADE'), primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id', ondelete='CASCADE'), primary_key=True)
    weight: Mapped[float] = mapped_column(Float)

class GameSession(Base):
    __tablename__ = 'game_sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    status: Mapped[str] = mapped_column(String(32), default='active')
    question_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    guessed_entity_id: Mapped[int | None] = mapped_column(ForeignKey('entities.id'))
    engine_state: Mapped[dict] = mapped_column(JSONB, default=dict)

class GameAnswer(Base):
    __tablename__ = 'game_answers'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('game_sessions.id', ondelete='CASCADE'))
    question_id: Mapped[int] = mapped_column(ForeignKey('questions.id'))
    answer_value: Mapped[float] = mapped_column(Float)
    question_number: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PendingEntity(Base):
    __tablename__ = 'pending_entities'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_telegram_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    title: Mapped[str] = mapped_column(String(128))
    username: Mapped[str | None] = mapped_column(String(64))
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    proposed_question: Mapped[str | None] = mapped_column(Text)
    ownership_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default='pending')
    moderator_telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    moderator_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class EntityReport(Base):
    __tablename__ = 'entity_reports'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    entity_id: Mapped[int] = mapped_column(ForeignKey('entities.id', ondelete='CASCADE'))
    telegram_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id', ondelete='CASCADE'))
    reason: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint('entity_id', 'telegram_id'),)

class CoinTransaction(Base):
    __tablename__ = 'coin_transactions'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    amount: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(String(64))
    reference_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default='completed')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int | None] = mapped_column(ForeignKey('entities.id'))
    channel_username: Mapped[str | None] = mapped_column(String(64))
    channel_id: Mapped[int | None] = mapped_column(BigInteger)
    reward_coins: Mapped[int] = mapped_column(Integer, default=50)
    hold_hours: Mapped[int] = mapped_column(Integer, default=48)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class UserTask(Base):
    __tablename__ = 'user_tasks'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'), primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey('tasks.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default='started')
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rewarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class ShopItem(Base):
    __tablename__ = 'shop_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(32))
    price_coins: Mapped[int] = mapped_column(BigInteger)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class UserInventory(Base):
    __tablename__ = 'user_inventory'
    user_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'), primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey('shop_items.id'), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)

class ShopTransaction(Base):
    __tablename__ = 'shop_transactions'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    item_id: Mapped[int] = mapped_column(ForeignKey('shop_items.id'))
    price_coins: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PromotionCampaign(Base):
    __tablename__ = 'promotion_campaigns'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[int] = mapped_column(ForeignKey('entities.id', ondelete='CASCADE'))
    owner_telegram_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    impressions_total: Mapped[int] = mapped_column(Integer, default=4500)
    impressions_used: Mapped[int] = mapped_column(Integer, default=0)
    clicks_total: Mapped[int] = mapped_column(Integer, default=0)
    price_rub: Mapped[int] = mapped_column(Integer, default=180)
    status: Mapped[str] = mapped_column(String(32), default='pending_payment')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class PromotionImpression(Base):
    __tablename__ = 'promotion_impressions'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('promotion_campaigns.id', ondelete='CASCADE'))
    telegram_id: Mapped[int | None] = mapped_column(ForeignKey('users.telegram_id'))
    game_session_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('game_sessions.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PromotionClick(Base):
    __tablename__ = 'promotion_clicks'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('promotion_campaigns.id', ondelete='CASCADE'))
    telegram_id: Mapped[int | None] = mapped_column(ForeignKey('users.telegram_id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    telegram_id: Mapped[int] = mapped_column(ForeignKey('users.telegram_id'))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('promotion_campaigns.id'))
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default='RUB')
    status: Mapped[str] = mapped_column(String(32))
    provider_payment_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

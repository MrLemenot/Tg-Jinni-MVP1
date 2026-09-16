from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from app.config.settings import get_settings


def normalize_database_url(value: str) -> str:
    """Render/Postgres usually gives postgresql://; async SQLAlchemy needs asyncpg."""
    value = value.strip()
    if value.startswith("postgres://"):
        value = "postgresql://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        value = "postgresql+asyncpg://" + value[len("postgresql://"):]
    if value.startswith("postgresql+psycopg2://"):
        value = "postgresql+asyncpg://" + value[len("postgresql+psycopg2://"):]
    return value


settings = get_settings()
database_url = normalize_database_url(settings.database_url)
engine_kwargs = {"pool_pre_ping": True}
if not database_url.startswith("sqlite"):
    engine_kwargs.update(pool_size=5, max_overflow=5)
engine = create_async_engine(database_url, **engine_kwargs)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with SessionLocal() as session:
        yield session

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings
from src.db.models import Base

async_engine = create_async_engine(settings.DATABASE_URL, echo=False)
session_factory = async_sessionmaker(async_engine, expire_on_commit=False)


async def initdb() -> None:
    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def init_db() -> None:
    await initdb()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session

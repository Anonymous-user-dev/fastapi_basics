from sqlmodel import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine
from src.config import settings

engine = AsyncEngine(
    create_engine(
        settings.DB_URL,
        echo=True
    )
)

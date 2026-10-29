import asyncio
from pathlib import Path
from typing import Annotated

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import redis as redis_store
from src.db.main import get_session

health_router = APIRouter(prefix="/health", tags=["health"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PROJECT_ROOT = Path(__file__).resolve().parent.parent
alembic_config = Config(str(PROJECT_ROOT / "alembic.ini"))
alembic_config.set_main_option(
    "script_location",
    str(PROJECT_ROOT / "migrations"),
)
EXPECTED_DATABASE_REVISION = ScriptDirectory.from_config(
    alembic_config
).get_current_head()


async def check_database(session: AsyncSession) -> None:
    database_revision = await session.scalar(
        text("SELECT version_num FROM alembic_version")
    )
    if database_revision != EXPECTED_DATABASE_REVISION:
        raise RuntimeError(
            "Database migration does not match the application revision"
        )


async def check_redis() -> None:
    if redis_store.token_blocklist is not None:
        await redis_store.token_blocklist.ping()


@health_router.get("/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@health_router.get("/ready")
async def readiness(
    response: Response,
    session: SessionDep,
) -> dict:
    database_result, redis_result = await asyncio.gather(
        check_database(session),
        check_redis(),
        return_exceptions=True,
    )
    checks = {
        "database": (
            "unavailable" if isinstance(database_result, Exception) else "ok"
        ),
        "redis": "unavailable" if isinstance(redis_result, Exception) else "ok",
    }
    if "unavailable" in checks.values():
        response.status_code = 503
        return {"status": "not_ready", "checks": checks}
    return {"status": "ready", "checks": checks}

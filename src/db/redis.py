import redis.asyncio as redis

from src.config import settings

JTI_EXPIRY = 3600
_memory_blocklist: set[str] = set()
token_blocklist = None if settings.REDIS_URL.startswith("memory://") else redis.from_url(settings.REDIS_URL)


async def add_jti_to_blocklist(jti: str) -> None:
    if token_blocklist is None:
        _memory_blocklist.add(jti)
        return
    await token_blocklist.set(name=jti, value="", ex=JTI_EXPIRY)


async def token_in_blocklist(jti: str) -> bool:
    if token_blocklist is None:
        return jti in _memory_blocklist
    return await token_blocklist.get(jti) is not None

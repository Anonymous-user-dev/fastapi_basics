from time import monotonic

import redis.asyncio as redis

from src.config import settings

JTI_EXPIRY = 3600
_memory_blocklist: set[str] = set()
_memory_session_blocklist: set[str] = set()
_memory_rate_limits: dict[str, tuple[int, float]] = {}
token_blocklist = None if settings.REDIS_URL.startswith("memory://") else redis.from_url(settings.REDIS_URL)
RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


async def add_jti_to_blocklist(jti: str, expires_in: int = JTI_EXPIRY) -> None:
    if token_blocklist is None:
        _memory_blocklist.add(jti)
        return
    await token_blocklist.set(name=f"token:{jti}", value="", ex=expires_in)


async def token_in_blocklist(jti: str) -> bool:
    if token_blocklist is None:
        return jti in _memory_blocklist
    return await token_blocklist.get(f"token:{jti}") is not None


async def consume_refresh_token(jti: str, expires_in: int) -> bool:
    """Mark a refresh token as used and report whether it was still unused."""
    if token_blocklist is None:
        if jti in _memory_blocklist:
            return False
        _memory_blocklist.add(jti)
        return True
    return bool(
        await token_blocklist.set(
            name=f"token:{jti}",
            value="",
            ex=expires_in,
            nx=True,
        )
    )


async def revoke_session(session_id: str, expires_in: int) -> None:
    if token_blocklist is None:
        _memory_session_blocklist.add(session_id)
        return
    await token_blocklist.set(
        name=f"session:{session_id}",
        value="",
        ex=expires_in,
    )


async def session_is_revoked(session_id: str) -> bool:
    if token_blocklist is None:
        return session_id in _memory_session_blocklist
    return await token_blocklist.get(f"session:{session_id}") is not None


async def rate_limit_allows(key: str, limit: int, window_seconds: int) -> bool:
    if token_blocklist is None:
        now = monotonic()
        count, expires_at = _memory_rate_limits.get(key, (0, now + window_seconds))
        if now >= expires_at:
            count, expires_at = 0, now + window_seconds
        count += 1
        _memory_rate_limits[key] = (count, expires_at)
        return count <= limit

    redis_key = f"rate:{key}"
    count = await token_blocklist.eval(
        RATE_LIMIT_SCRIPT,
        1,
        redis_key,
        window_seconds,
    )
    return count <= limit

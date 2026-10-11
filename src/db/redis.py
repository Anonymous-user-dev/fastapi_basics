import redis.asyncio as redis

from src.config import settings

JTI_EXPIRY = 3600
_memory_blocklist: set[str] = set()
_memory_session_blocklist: set[str] = set()
token_blocklist = None if settings.REDIS_URL.startswith("memory://") else redis.from_url(settings.REDIS_URL)


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

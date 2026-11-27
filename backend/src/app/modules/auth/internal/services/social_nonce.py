"""Single-use sign-in nonces: ``nonce:social:{nonce}`` in Redis for 5 minutes, taken with
``GETDEL`` so a nonce can be used once (05 §C.5 step 2)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from redis.exceptions import RedisError

from app.core.errors import UnauthorizedError, UnavailableError
from app.core.redis import get_redis

TTL = timedelta(minutes=5)


def key(nonce: str) -> str:
    return f"nonce:social:{nonce}"


async def issue(provider: str, now: datetime) -> tuple[str, datetime]:
    nonce = secrets.token_urlsafe(32)
    try:
        await get_redis().set(key(nonce), provider, ex=int(TTL.total_seconds()))
    except (RedisError, OSError) as exc:
        raise UnavailableError("Sign-in is unavailable; try again shortly") from exc
    return nonce, now + TTL


async def consume(nonce: str, provider: str) -> None:
    try:
        stored = await get_redis().getdel(key(nonce))
    except (RedisError, OSError) as exc:
        raise UnavailableError("Sign-in is unavailable; try again shortly") from exc
    if isinstance(stored, bytes):
        stored = stored.decode()
    if stored != provider:
        raise UnauthorizedError("Start the sign-in again", code="invalid_nonce")

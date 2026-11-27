"""Redis client: rate limits, quotas, leaderboards, exam locks and caches (v2 §0.2).

Redis is never the system of record; everything in it can be rebuilt (v2 §3.6).
Creating the client does not connect; the first command does.
"""

from functools import lru_cache

from redis.asyncio import Redis

from app.core.settings import get_settings


@lru_cache
def get_redis() -> Redis:
    return Redis.from_url(get_settings().redis_url, decode_responses=True)


async def ping_redis() -> None:
    """Readiness check: one PING to Redis."""
    await get_redis().ping()

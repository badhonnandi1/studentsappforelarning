"""Process-wide async Redis client with small typed helpers."""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

_client: Redis | None = None


def init_redis(url: str) -> Redis:
    global _client
    _client = Redis.from_url(url, socket_timeout=2.0, socket_connect_timeout=2.0)
    return _client


def use_client(client: Redis | None) -> None:
    """Install an existing client (tests, or a shared client in workers)."""
    global _client
    _client = client


def get_redis() -> Redis:
    if _client is None:
        raise RuntimeError("redis not initialised; call init_redis() at startup")
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def ping_redis() -> None:
    await get_redis().ping()


async def get_json(key: str, client: Redis | None = None) -> Any | None:
    raw = await (client or get_redis()).get(key)
    return None if raw is None else json.loads(raw)


async def set_json(key: str, value: Any, ttl_s: int, client: Redis | None = None) -> None:
    await (client or get_redis()).set(key, json.dumps(value, separators=(",", ":")), ex=ttl_s)

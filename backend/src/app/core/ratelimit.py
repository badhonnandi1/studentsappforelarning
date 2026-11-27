"""Sliding-window rate limits in Redis (14 §1.7 tiers).

Each rule is a sorted set of request timestamps; one Lua call trims, counts and records
atomically. A tier is a list of rules on different keys (IP, user, device, phone). When Redis
is unreachable a tier either fails open (reads) or closed (OTP send), per its definition.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

import structlog
from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.errors import TooManyRequestsError, UnavailableError
from app.core.redis import get_redis

log = structlog.get_logger(__name__)

_SCRIPT = """
local key, now, window, limit, member = KEYS[1], tonumber(ARGV[1]), tonumber(ARGV[2]),
  tonumber(ARGV[3]), ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count < limit then
  redis.call('ZADD', key, now, member)
  redis.call('PEXPIRE', key, window)
  return {1, limit - count - 1}
end
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
return {0, tonumber(oldest[2]) + window - now}
"""


@dataclass(frozen=True)
class Rule:
    scope: str  # which key from the key map: ip, user, device, phone, provider
    limit: int
    window_s: int


@dataclass(frozen=True)
class Tier:
    name: str
    rules: tuple[Rule, ...]
    fail_open: bool = True


TIERS: dict[str, Tier] = {
    t.name: t
    for t in (
        Tier("otp_ip", (Rule("ip", 10, 3600), Rule("device", 10, 3600)), fail_open=False),
        Tier("otp_phone", (Rule("phone", 3, 900), Rule("phone", 5, 86400)), fail_open=False),
        Tier("auth", (Rule("ip", 20, 60), Rule("device", 10, 60))),
        Tier("write", (Rule("user", 120, 60),)),
        Tier("answer", (Rule("user", 60, 60),)),
        Tier("read", (Rule("user", 600, 60),)),
        Tier("ai", (Rule("user", 10, 60),)),
        Tier("upload", (Rule("user", 30, 3600),)),
        Tier("admin", (Rule("user", 300, 60),)),
        Tier("webhook", (Rule("provider", 1000, 60),)),
    )
}
_overrides: dict[str, Tier] = {}


def set_tier_overrides(tiers: Mapping[str, Tier]) -> None:
    """Called by the platform module when runtime_config changes the limits."""
    _overrides.clear()
    _overrides.update(tiers)


def get_tier(name: str) -> Tier:
    return _overrides.get(name) or TIERS[name]


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after_s: int
    remaining: int


async def hit(redis: Redis, key: str, rule: Rule, now_ms: int | None = None) -> Decision:
    now = now_ms if now_ms is not None else time.time_ns() // 1_000_000
    window_ms = rule.window_s * 1000
    member = f"{now}-{uuid.uuid4().hex[:8]}"
    allowed, value = await redis.eval(_SCRIPT, 1, key, now, window_ms, rule.limit, member)
    if int(allowed) == 1:
        return Decision(True, 0, int(value))
    return Decision(False, max(1, -(-int(value) // 1000)), 0)


async def enforce(
    tier_name: str,
    keys: Mapping[str, str],
    *,
    redis: Redis | None = None,
    now_ms: int | None = None,
) -> None:
    """Apply every rule of the tier whose scope has a key; raise 429 on the first refusal."""
    tier = get_tier(tier_name)
    try:
        client = redis or get_redis()
        for index, rule in enumerate(tier.rules):
            value = keys.get(rule.scope)
            if not value:
                continue
            key = f"rl:{tier.name}:{index}:{rule.scope}:{value}"
            decision = await hit(client, key, rule, now_ms)
            if not decision.allowed:
                raise TooManyRequestsError("Too many requests", retry_after=decision.retry_after_s)
    except (RedisError, OSError) as exc:
        if tier.fail_open:
            log.warning("ratelimit_unavailable_fail_open", tier=tier.name, error=type(exc).__name__)
            return
        raise UnavailableError("Rate limiter unavailable") from exc


def client_ip(request: Request) -> str:
    """Cloudflare sets ``CF-Connecting-IP``; the edge strips client-supplied copies."""
    forwarded = request.headers.get("cf-connecting-ip")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else "unknown"


KeyFn = Callable[[Request], Mapping[str, str]]


def ip_and_device(request: Request) -> Mapping[str, str]:
    return {"ip": client_ip(request), "device": request.headers.get("x-device-id", "")}


def rate_limit(tier: str, key_fn: KeyFn = ip_and_device) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency for tiers keyed from the request alone (IP, device header)."""
    get_tier(tier)  # fail at import time on a typo

    async def dependency(request: Request) -> None:
        await enforce(tier, key_fn(request))

    return dependency

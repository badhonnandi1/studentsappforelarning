"""Circuit breaker (shared state in Redis) and retry with exponential backoff and jitter.

Breaker: opens when at least ``min_calls`` calls in the last 30 s failed at a rate of 50% or
more. While open, calls fail fast with ``CircuitOpenError``. After the cooldown one probe is let
through (half-open); its success closes the breaker, its failure reopens it.
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis

from app.core.errors import UnavailableError


class CircuitOpenError(UnavailableError):
    code = "unavailable"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        redis: Redis,
        *,
        window_s: int = 30,
        error_ratio: float = 0.5,
        min_calls: int = 10,
        cooldown_s: int = 30,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.name, self.redis = name, redis
        self.window_ms, self.cooldown_ms = window_s * 1000, cooldown_s * 1000
        self.error_ratio, self.min_calls = error_ratio, min_calls
        self.clock = clock
        self._ok, self._err = f"cb:{name}:ok", f"cb:{name}:err"
        self._open, self._probe = f"cb:{name}:open_until", f"cb:{name}:probe"

    def _now_ms(self) -> int:
        return int(self.clock() * 1000)

    async def state(self) -> str:
        open_until = await self.redis.get(self._open)
        if open_until is None:
            return "closed"
        return "open" if self._now_ms() < int(open_until) else "half_open"

    async def _before(self) -> bool:
        """Return True when this call is the half-open probe."""
        state = await self.state()
        if state == "closed":
            return False
        if state == "half_open" and await self.redis.set(self._probe, "1", nx=True, px=10_000):
            return True
        raise CircuitOpenError(f"{self.name} is unavailable")

    async def _record(self, key: str) -> None:
        now = self._now_ms()
        pipe = self.redis.pipeline()
        pipe.zadd(key, {f"{now}-{uuid.uuid4().hex[:6]}": now})
        for k in (self._ok, self._err):
            pipe.zremrangebyscore(k, "-inf", now - self.window_ms)
            pipe.pexpire(k, self.window_ms)
        await pipe.execute()

    async def _trip(self) -> None:
        await self.redis.set(self._open, self._now_ms() + self.cooldown_ms, px=self.window_ms * 10)
        await self.redis.delete(self._probe)

    async def _reset(self) -> None:
        await self.redis.delete(self._open, self._probe, self._ok, self._err)

    async def on_success(self, probe: bool = False) -> None:
        if probe:
            await self._reset()
            return
        await self._record(self._ok)

    async def on_failure(self, probe: bool = False) -> None:
        if probe:
            await self._trip()
            return
        await self._record(self._err)
        ok, err = await self.redis.zcard(self._ok), await self.redis.zcard(self._err)
        total = ok + err
        if total >= self.min_calls and err / total >= self.error_ratio:
            await self._trip()

    async def call[T](self, fn: Callable[[], Awaitable[T]]) -> T:
        probe = await self._before()
        try:
            result = await fn()
        except Exception:
            await self.on_failure(probe)
            raise
        await self.on_success(probe)
        return result


def backoff_delay(
    attempt: int,
    *,
    base_s: float = 0.2,
    cap_s: float = 5.0,
    jitter: float = 0.2,
    rand: Callable[[], float] = random.random,
) -> float:
    """``base * 2^attempt`` capped, then ±jitter (attempt counts from 0)."""
    delay = min(cap_s, base_s * (2.0**attempt))
    return max(0.0, delay * (1 + jitter * (2 * rand() - 1)))


async def retry_async[T](
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    base_s: float = 0.2,
    cap_s: float = 5.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    for attempt in range(attempts):
        try:
            return await fn()
        except CircuitOpenError:
            raise
        except retry_on:
            if attempt == attempts - 1:
                raise
            await sleep(backoff_delay(attempt, base_s=base_s, cap_s=cap_s))
    raise AssertionError("unreachable")  # pragma: no cover

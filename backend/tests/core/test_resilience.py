import contextlib

import pytest
from redis.asyncio import Redis

from app.core.resilience import CircuitBreaker, CircuitOpenError, backoff_delay, retry_async

pytestmark = pytest.mark.integration


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


async def ok() -> str:
    return "ok"


async def fail() -> str:
    raise ConnectionError("down")


async def run(breaker: CircuitBreaker, fn: object) -> None:
    with contextlib.suppress(ConnectionError):
        await breaker.call(fn)  # type: ignore[arg-type]


async def test_breaker_opens_at_half_errors_then_probes_and_closes(redis: Redis) -> None:
    clock = Clock()
    breaker = CircuitBreaker("sms", redis, min_calls=10, cooldown_s=30, clock=clock)
    for _ in range(5):
        await run(breaker, ok)
    for _ in range(4):
        await run(breaker, fail)
    assert await breaker.state() == "closed"  # 9 calls: below min volume
    await run(breaker, fail)  # 10 calls, 50% errors
    assert await breaker.state() == "open"
    with pytest.raises(CircuitOpenError):
        await breaker.call(ok)
    clock.t += 31
    assert await breaker.state() == "half_open"
    assert await breaker.call(ok) == "ok"  # the probe succeeds
    assert await breaker.state() == "closed"


async def test_failed_probe_reopens(redis: Redis) -> None:
    clock = Clock()
    breaker = CircuitBreaker("fb", redis, min_calls=2, cooldown_s=10, clock=clock)
    await run(breaker, fail)
    await run(breaker, fail)
    assert await breaker.state() == "open"
    clock.t += 11
    await run(breaker, fail)  # the probe fails
    assert await breaker.state() == "open"


async def test_only_one_probe_in_half_open(redis: Redis) -> None:
    clock = Clock()
    breaker = CircuitBreaker("g", redis, min_calls=1, cooldown_s=5, clock=clock)
    await run(breaker, fail)
    clock.t += 6
    assert await breaker._before() is True
    with pytest.raises(CircuitOpenError):
        await breaker._before()


async def test_old_errors_leave_the_window(redis: Redis) -> None:
    clock = Clock()
    breaker = CircuitBreaker("w", redis, min_calls=4, clock=clock)
    for _ in range(3):
        await run(breaker, fail)
    clock.t += 31
    for _ in range(3):
        await run(breaker, ok)
    await run(breaker, fail)  # 1 of 4 in the window
    assert await breaker.state() == "closed"


def test_backoff_bounds() -> None:
    assert backoff_delay(0, rand=lambda: 0.5) == pytest.approx(0.2)
    assert backoff_delay(3, rand=lambda: 0.5) == pytest.approx(1.6)
    assert backoff_delay(10, rand=lambda: 0.5) == pytest.approx(5.0)
    assert backoff_delay(2, rand=lambda: 1.0) == pytest.approx(0.8 * 1.2)
    assert backoff_delay(2, rand=lambda: 0.0) == pytest.approx(0.8 * 0.8)


async def test_retry_async_retries_then_succeeds_or_raises() -> None:
    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)

    calls = 0

    async def flaky() -> int:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError
        return calls

    assert await retry_async(flaky, attempts=3, sleep=sleep) == 3
    assert len(sleeps) == 2
    with pytest.raises(ConnectionError):
        await retry_async(fail, attempts=2, sleep=sleep)


async def test_retry_never_retries_open_circuit() -> None:
    calls = 0

    async def open_circuit() -> None:
        nonlocal calls
        calls += 1
        raise CircuitOpenError("open")

    with pytest.raises(CircuitOpenError):
        await retry_async(open_circuit, attempts=5)
    assert calls == 1

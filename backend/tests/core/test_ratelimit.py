import httpx
import pytest
from fastapi import Depends, FastAPI
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import ratelimit
from app.core import redis as core_redis
from app.core.errors import TooManyRequestsError, UnavailableError, add_error_handlers
from app.core.ratelimit import Rule, Tier, enforce, hit

pytestmark = pytest.mark.integration


async def test_sliding_window_allows_n_then_blocks(redis: Redis) -> None:
    rule = Rule("ip", 3, 60)
    now = 1_000_000
    for i in range(3):
        decision = await hit(redis, "k", rule, now + i)
        assert decision.allowed
        assert decision.remaining == 2 - i
    blocked = await hit(redis, "k", rule, now + 10)
    assert not blocked.allowed
    assert blocked.retry_after_s == 60  # oldest entry leaves the window after ~60 s


async def test_window_slides(redis: Redis) -> None:
    rule = Rule("ip", 2, 10)
    assert (await hit(redis, "s", rule, 0)).allowed
    assert (await hit(redis, "s", rule, 5_000)).allowed
    assert not (await hit(redis, "s", rule, 9_000)).allowed
    assert (await hit(redis, "s", rule, 10_001)).allowed  # the first hit has left the window


async def test_enforce_raises_with_retry_after_and_isolates_keys(redis: Redis) -> None:
    for _ in range(10):
        await enforce("otp_ip", {"ip": "1.1.1.1"}, redis=redis, now_ms=0)
    with pytest.raises(TooManyRequestsError) as caught:
        await enforce("otp_ip", {"ip": "1.1.1.1"}, redis=redis, now_ms=1000)
    assert caught.value.headers == {"Retry-After": "3599"}
    await enforce("otp_ip", {"ip": "2.2.2.2"}, redis=redis, now_ms=1000)


async def test_missing_key_scope_is_skipped(redis: Redis) -> None:
    for _ in range(30):
        await enforce("auth", {"ip": "", "device": ""}, redis=redis)


class BrokenRedis:
    async def eval(self, *_args: object) -> None:
        raise RedisConnectionError("down")


async def test_redis_down_fails_open_for_reads_and_closed_for_otp() -> None:
    broken = BrokenRedis()
    await enforce("read", {"user": "u1"}, redis=broken)  # type: ignore[arg-type]
    with pytest.raises(UnavailableError):
        await enforce("otp_phone", {"phone": "h"}, redis=broken)  # type: ignore[arg-type]


async def test_overrides_replace_tiers(redis: Redis) -> None:
    ratelimit.set_tier_overrides({"read": Tier("read", (Rule("user", 1, 60),))})
    try:
        await enforce("read", {"user": "u"}, redis=redis)
        with pytest.raises(TooManyRequestsError):
            await enforce("read", {"user": "u"}, redis=redis)
    finally:
        ratelimit.set_tier_overrides({})
    assert ratelimit.get_tier("read").rules[0].limit == 600


async def test_dependency_returns_429_with_retry_after(redis: Redis) -> None:
    core_redis.use_client(redis)
    app = FastAPI()
    add_error_handlers(app)

    @app.post("/login", dependencies=[Depends(ratelimit.rate_limit("auth"))])
    async def login() -> dict[str, bool]:
        return {"ok": True}

    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
            headers = {"x-device-id": "dev-1", "cf-connecting-ip": "9.9.9.9"}
            codes = [(await client.post("/login", headers=headers)).status_code for _ in range(11)]
            assert codes[:10] == [200] * 10
            last = await client.post("/login", headers=headers)
            assert last.status_code == 429
            assert int(last.headers["Retry-After"]) >= 1
    finally:
        core_redis.use_client(None)


def test_unknown_tier_fails_fast() -> None:
    with pytest.raises(KeyError):
        ratelimit.rate_limit("nope")


async def test_client_ip_falls_back_to_socket() -> None:
    from starlette.requests import Request

    request = Request({"type": "http", "headers": [], "client": ("10.0.0.1", 1)})
    assert ratelimit.client_ip(request) == "10.0.0.1"
    assert ratelimit.client_ip(Request({"type": "http", "headers": []})) == "unknown"

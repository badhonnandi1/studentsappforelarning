"""The HTTP gateway adapter and its circuit breaker; the fake's logging rule."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from structlog.testing import capture_logs

from app.core.resilience import CircuitBreaker, CircuitOpenError
from app.core.settings import Settings
from app.modules.plan.internal import providers
from app.modules.plan.internal.providers.sms_base import SmsGatewayError
from app.modules.plan.internal.providers.sms_fake import FakeSmsGateway
from app.modules.plan.internal.providers.sms_http import HttpSmsGateway

pytestmark = pytest.mark.integration
PHONE = "+8801712345678"
SETTINGS = Settings(
    _env_file=None,
    sms_backend="http",
    sms_api_url="https://sms.example.test/send",
    sms_api_key=SecretStr("k" * 32),
    sms_sender_id="StudyApp",
)


def gateway(handler: httpx.MockTransport, redis: Redis) -> HttpSmsGateway:
    client = httpx.AsyncClient(transport=handler)
    breaker = CircuitBreaker("sms_test", redis, min_calls=2, cooldown_s=60)
    return HttpSmsGateway(SETTINGS, client=client, breaker=breaker)


async def test_posts_and_parses(app_redis: Redis) -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"message_id": 77, "cost_poisha": 45})

    result = await gateway(httpx.MockTransport(handle), app_redis).send(PHONE, "কোড 123456")
    assert (result.provider_msg_id, result.cost_poisha, result.status) == ("77", 45, "sent")
    body = json.loads(seen[0].content)
    assert body == {"to": PHONE, "sender_id": "StudyApp", "message": "কোড 123456"}
    assert seen[0].headers["Authorization"] == "Bearer " + "k" * 32


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(500, text=f"bad number {PHONE}"), "returned 500"),
        (httpx.Response(200, text="not json"), "invalid JSON"),
    ],
)
async def test_errors_never_carry_the_phone(
    app_redis: Redis, response: httpx.Response, message: str
) -> None:
    g = gateway(httpx.MockTransport(lambda _r: response), app_redis)
    with pytest.raises(SmsGatewayError, match=message) as info:
        await g.send(PHONE, "hello")
    assert PHONE not in str(info.value)


async def test_unreachable_and_breaker_opens(app_redis: Redis) -> None:
    calls = 0

    def handle(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("refused")

    g = gateway(httpx.MockTransport(handle), app_redis)
    for _ in range(2):
        with pytest.raises(SmsGatewayError, match="unreachable: ConnectError"):
            await g.send(PHONE, "hello")
    with pytest.raises(CircuitOpenError):
        await g.send(PHONE, "hello")
    assert calls == 2  # fails fast while open
    empty = await gateway(
        httpx.MockTransport(lambda _r: httpx.Response(200, json={})), app_redis
    )._post(PHONE, "x")
    assert (empty.provider_msg_id, empty.cost_poisha) == (None, None)


async def test_default_breaker_and_gateway_selection(app_redis: Redis) -> None:
    assert isinstance(HttpSmsGateway(SETTINGS)._breaker(), CircuitBreaker)
    providers.use_gateway(None)
    try:
        assert isinstance(providers.gateway(), FakeSmsGateway)  # test env uses the fake
    finally:
        providers.use_gateway(None)


async def test_fake_logs_body_only_locally() -> None:
    deployed = FakeSmsGateway(Settings(_env_file=None))
    object.__setattr__(deployed.settings, "app_env", "staging")
    with capture_logs() as logs:
        await deployed.send(PHONE, "code 999111")
        local = FakeSmsGateway(Settings(_env_file=None))
        await local.send(PHONE, "no digits here")
    assert [entry.get("sms_body") for entry in logs] == ["no digits here"]
    assert deployed.last_code(PHONE) == "999111"
    assert local.last_code(PHONE) is None

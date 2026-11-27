"""``POST /v1/auth/otp/send`` (05 §E: normalisation, T-otp limits, challenge, no enumeration)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import use_client
from app.modules.auth.internal.models import OtpChallenge
from app.modules.auth.internal.services import otp_send
from tests.modules.auth.conftest import PHONE, send, sign_up, verify
from tests.support.users import make_user

pytestmark = [pytest.mark.api, pytest.mark.db]


@pytest.mark.parametrize(
    "raw", ["01700000001", "+8801700000001", "8801700000001", "০১৭০০০০০০০১", "017-0000-0001"]
)
async def test_phone_forms_normalise(client: httpx.AsyncClient, raw: str) -> None:
    response = await send(client, raw)
    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body) == {"challenge_id", "expires_at", "resend_after_s"}
    assert body["resend_after_s"] == otp_send.RESEND_AFTER_S


@pytest.mark.parametrize("raw", ["12345", "+8801212345678", "+919876543210", "01712345"])
async def test_invalid_phone(client: httpx.AsyncClient, raw: str) -> None:
    response = await send(client, raw)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_phone"


async def test_challenge_row_holds_no_plain_phone_or_code(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await send(client)
    row = (await session.execute(select(OtpChallenge))).scalar_one()
    assert PHONE.encode() not in row.phone_enc
    assert b"123456" not in row.code_hash
    assert row.sms_message_id is not None
    assert row.purpose == "sign_in"


async def test_same_response_for_known_and_unknown_numbers(client: httpx.AsyncClient) -> None:
    await sign_up(client, "+8801700000002")
    known = await send(client, "+8801700000002", device="device-0002")
    unknown = await send(client, "+8801700000003", device="device-0003")
    assert known.status_code == unknown.status_code == 202
    assert set(known.json()) == set(unknown.json())


async def test_phone_limit_three_per_fifteen_minutes(client: httpx.AsyncClient) -> None:
    for i in range(3):
        assert (await send(client, device=f"device-000{i}")).status_code == 202
    refused = await send(client, device="device-0009")
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0


async def test_ip_limit_ten_per_hour(client: httpx.AsyncClient) -> None:
    for i in range(10):
        response = await send(client, f"+88017000001{i:02d}", device=f"device-1{i:03d}")
        assert response.status_code == 202
    assert (await send(client, "+8801700000999", device="device-2000")).status_code == 429


async def test_device_limit_ten_per_hour(client: httpx.AsyncClient) -> None:
    for i in range(10):
        headers = {"CF-Connecting-IP": f"198.51.100.{i}"}
        body = {"phone": f"+88017000002{i:02d}", "device_id": "device-same"}
        assert (await client.post("/v1/auth/otp/send", json=body, headers=headers)).is_success
    body = {"phone": "+8801700000300", "device_id": "device-same"}
    late = await client.post("/v1/auth/otp/send", json=body, headers={"CF-Connecting-IP": "x"})
    assert late.status_code == 429


async def test_challenge_required_after_three_failures(client: httpx.AsyncClient) -> None:
    sent = await send(client)
    for _ in range(3):
        assert (await verify(client, sent.json()["challenge_id"], "000000")).status_code == 401
    refused = await send(client, device="device-0002")
    assert refused.status_code == 403
    error = refused.json()["error"]
    assert error["code"] == "challenge_required"
    assert "challenge_url" in error["details"]
    wrong = await send(client, device="device-0003", challenge_token="nope")
    assert wrong.status_code == 403
    passed = await send(client, device="device-0004", challenge_token="local-pass")
    assert passed.status_code == 202


async def test_suspended_number_refused(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    async with sessions() as setup, setup.begin():
        await make_user(setup, phone="+8801700000005", status="suspended")
    response = await send(client, "+8801700000005")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_redis_down_fails_closed(client: httpx.AsyncClient, session: AsyncSession) -> None:
    use_client(Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2))
    response = await send(client)
    assert response.status_code == 503
    count = (await session.execute(select(func.count()).select_from(OtpChallenge))).scalar_one()
    assert count == 0

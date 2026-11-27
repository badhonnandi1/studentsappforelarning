"""``POST /v1/auth/otp/verify`` and ``/v1/auth/sign-up/complete`` (05 §E, R-24)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.auth.internal.models import (
    DeviceSession,
    OtpChallenge,
    PrivacySetting,
    RefreshToken,
    RoleGrant,
    User,
)
from app.modules.nfr.internal.models import OutboxEvent
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.conftest import PHONE, send, sign_in, sign_up, verify
from tests.support.users import make_user

pytestmark = [pytest.mark.api, pytest.mark.db]


async def count(session: AsyncSession, model: type) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_new_number_needs_profile_and_creates_nothing(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    sent = await send(client)
    response = await verify(client, sent.json()["challenge_id"])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_profile"
    assert body["required"] == ["date_of_birth"]
    assert len(body["pending_signup_token"]) >= 32
    assert await count(session, User) == 0


async def test_sign_up_creates_user_defaults_session_audit_and_event(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    pair = await sign_up(client)
    assert set(pair) >= {"access_token", "refresh_token", "session_id", "user"}
    assert pair["user"]["roles"] == ["student"]
    assert pair["user"]["is_minor"] is False
    assert pair["user"]["needs_profile"] is True
    user = (await session.execute(select(User))).scalar_one()
    assert user.phone_hash is not None
    assert PHONE.encode() not in (user.phone_enc or b"")
    privacy = await session.get(PrivacySetting, user.id)
    assert privacy is not None
    assert privacy.profile_private
    assert privacy.leaderboard_visible
    grant = (await session.execute(select(RoleGrant))).scalar_one()
    assert (grant.role_code, grant.scope_type) == ("student", "global")
    assert await count(session, DeviceSession) == 1
    assert await count(session, RefreshToken) == 1
    audit = (await session.execute(select(AuditLog))).scalar_one()
    assert audit.action == "auth.session.sign_in"
    assert audit.after == {"method": "otp", "platform": "android", "created": True}
    event = (await session.execute(select(OutboxEvent))).scalar_one()
    assert event.event_type == "user.signed_in"
    assert event.payload["created"] is True


async def test_minor_needs_consent(client: httpx.AsyncClient) -> None:
    pair = await sign_up(client, dob="2012-05-01")
    assert pair["user"]["is_minor"] is True
    assert pair["user"]["needs_consent"] is True


async def test_existing_user_signs_in(client: httpx.AsyncClient, session: AsyncSession) -> None:
    await sign_up(client)
    pair = await sign_in(client, device_id="device-0002")
    assert pair["created"] is False
    assert pair["linked"] is False
    assert await count(session, User) == 1
    assert await count(session, DeviceSession) == 2


async def test_wrong_code_counts_attempts_then_429(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    challenge_id = (await send(client)).json()["challenge_id"]
    for left in (4, 3, 2, 1, 0):
        wrong = await verify(client, challenge_id, "000000")
        assert wrong.status_code == 401
        assert wrong.json()["error"]["code"] == "invalid_code"
        assert wrong.json()["error"]["details"]["attempts_left"] == left
    locked = await verify(client, challenge_id)
    assert locked.status_code == 429
    row = (await session.execute(select(OtpChallenge))).scalar_one()
    assert row.attempts == 5


async def test_expired_and_consumed_codes_are_gone(
    client: httpx.AsyncClient, clock: FrozenClock
) -> None:
    first = (await send(client)).json()["challenge_id"]
    clock.advance(minutes=6)
    assert (await verify(client, first)).status_code == 410
    second = (await send(client, device="device-0002")).json()["challenge_id"]
    assert (await verify(client, second)).status_code == 200
    assert (await verify(client, second)).status_code == 410


async def test_unknown_challenge_is_invalid(client: httpx.AsyncClient) -> None:
    response = await verify(client, "00000000-0000-7000-8000-000000000000")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_code"


async def test_suspended_user_cannot_finish_sign_in(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    async with sessions() as setup, setup.begin():
        user = await make_user(setup, phone=PHONE)
    challenge_id = (await send(client)).json()["challenge_id"]
    async with sessions() as setup, setup.begin():
        await setup.execute(update(User).where(User.id == user.id).values(status="suspended"))
    response = await verify(client, challenge_id)
    assert response.status_code == 403


async def test_sign_up_token_single_use_and_dob_checked(client: httpx.AsyncClient) -> None:
    sent = await send(client)
    token = (await verify(client, sent.json()["challenge_id"])).json()["pending_signup_token"]
    future = {"pending_signup_token": token, "date_of_birth": "2999-01-01"}
    bad = await client.post("/v1/auth/sign-up/complete", json=future)
    assert bad.status_code == 422
    good = {"pending_signup_token": token, "date_of_birth": "2001-02-03", "display_name": "রহিম"}
    done = await client.post("/v1/auth/sign-up/complete", json=good)
    assert done.status_code == 201
    assert done.json()["user"]["display_name"] == "রহিম"
    again = await client.post("/v1/auth/sign-up/complete", json=good)
    assert again.status_code == 410


async def test_sign_up_token_expires(client: httpx.AsyncClient, app_redis: Redis) -> None:
    sent = await send(client)
    token = (await verify(client, sent.json()["challenge_id"])).json()["pending_signup_token"]
    ttl = await app_redis.ttl(f"auth:pending_signup:{token}")
    assert 0 < ttl <= 900
    stored = await app_redis.get(f"auth:pending_signup:{token}")
    assert isinstance(stored, bytes)
    assert PHONE.encode() not in stored
    assert b"01700000001" not in stored
    await app_redis.delete(f"auth:pending_signup:{token}")
    late = {"pending_signup_token": token, "date_of_birth": "2001-02-03"}
    assert (await client.post("/v1/auth/sign-up/complete", json=late)).status_code == 410


async def test_codes_last_five_minutes(client: httpx.AsyncClient, clock: FrozenClock) -> None:
    sent = (await send(client)).json()
    clock.advance(timedelta(minutes=4, seconds=59))
    assert (await verify(client, sent["challenge_id"])).status_code == 200

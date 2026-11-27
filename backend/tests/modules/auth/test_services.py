"""AUTH service paths the HTTP tests do not reach: staff tokens, Redis outages, races."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnavailableError
from app.core.ids import uuid7
from app.core.redis import use_client
from app.core.security.actor import Actor
from app.core.security.jwt import token_keys
from app.modules.auth.internal.schemas.auth import DeviceInfo, SignUpCompleteIn
from app.modules.auth.internal.services import pending_signup, refresh, sign_in, summary, tokens
from app.modules.auth.internal.services import sessions as device_sessions
from tests.modules.auth.conftest import PHONE
from tests.support.users import make_user

pytestmark = pytest.mark.db
NOW = datetime(2026, 11, 27, 6, 0, tzinfo=UTC)
WEB = DeviceInfo(device_id="device-staff", platform="web")


def redis_down() -> None:
    use_client(Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2))


@pytest.mark.usefixtures("app_redis")
async def test_staff_sso_tokens_carry_mfa_and_do_not_slide(
    sessions: Callable[[], AsyncSession],
) -> None:
    async with sessions() as s, s.begin():
        user = await make_user(s)
        started = await sign_in.start_session(
            s, user, "sso", WEB, ip=None, now=NOW, audience="admin"
        )
    claims = token_keys().verify(started.pair.access_token, audience="admin", now=NOW)
    assert claims["sso"] is True
    assert claims["amr"] == ["mfa"]
    first_expiry = NOW + tokens.refresh_ttl("admin")
    later = NOW + timedelta(hours=1)
    async with sessions() as s:
        pair = await refresh.refresh(s, started.pair.refresh_token, later)
    again = token_keys().verify(pair.access_token, audience="admin", now=later)
    assert again["amr"] == ["mfa"]
    assert pair.refresh_expires_at == first_expiry


async def test_pending_signup_fails_closed_without_redis() -> None:
    redis_down()
    with pytest.raises(UnavailableError):
        await pending_signup.create_for_phone(PHONE, WEB)
    with pytest.raises(UnavailableError):
        await pending_signup.take("x" * 43)


async def test_revocation_cache_outage_is_logged_not_raised() -> None:
    redis_down()
    await tokens.mark_revoked([uuid7(), uuid7()])


@pytest.mark.usefixtures("app_redis")
async def test_complete_conflicts_when_the_number_signed_up_meanwhile(
    sessions: Callable[[], AsyncSession],
) -> None:
    first = await pending_signup.create_for_phone(PHONE, WEB)
    second = await pending_signup.create_for_phone(PHONE, WEB)
    dob = date(2000, 1, 1)
    async with sessions() as s:
        await pending_signup.complete(
            s,
            SignUpCompleteIn(pending_signup_token=first, date_of_birth=dob),
            ip="198.51.100.1",
            now=NOW,
        )
    async with sessions() as s:
        body = SignUpCompleteIn(pending_signup_token=second, date_of_birth=dob)
        with pytest.raises(ConflictError):
            await pending_signup.complete(s, body, ip="198.51.100.1", now=NOW)


async def test_no_date_of_birth_is_not_a_minor(session: AsyncSession) -> None:
    user = await make_user(session, date_of_birth=None)
    assert summary.is_minor(user, NOW) is False


@pytest.mark.usefixtures("app_redis")
async def test_logout_of_an_unknown_or_foreign_session_changes_nothing(
    sessions: Callable[[], AsyncSession],
) -> None:
    async with sessions() as s, s.begin():
        user = await make_user(s)
    actor = Actor(user_id=user.id, session_id=uuid7(), roles=frozenset({"student"}))
    async with sessions() as s:
        await device_sessions.logout(s, actor, NOW)
        assert await device_sessions.list_live(s, actor) == []

"""Step-up and phone change when Redis fails (503, never a silent pass)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnavailableError
from app.core.ids import uuid7
from app.core.redis import use_client
from app.core.security.actor import Actor
from app.modules.auth.internal.schemas.step_up import PhoneConfirmIn, PhoneStartIn, StepUpIn
from app.modules.auth.internal.services import otp_send, phone_change, step_up
from tests.modules.auth.conftest import PHONE, TEST_CODE
from tests.support.users import make_user

pytestmark = [pytest.mark.db, pytest.mark.usefixtures("app_redis")]


def redis_down() -> None:
    use_client(
        Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, retry=Retry(NoBackoff(), 0))
    )


async def phone_actor(sessions: Callable[[], AsyncSession]) -> Actor:
    async with sessions() as s, s.begin():
        user = await make_user(s, phone=PHONE)
    return Actor(user_id=user.id, session_id=uuid7(), roles=frozenset())


async def test_step_up_redis_down(sessions: Callable[[], AsyncSession]) -> None:
    actor, now = await phone_actor(sessions), datetime.now(UTC)
    async with sessions() as s:
        async with s.begin():
            row = await otp_send.issue(s, PHONE, "step_up", ip=None, device_id=None, now=now)
        body = StepUpIn(action="unlink", otp_challenge_id=row.id, code=TEST_CODE)
        redis_down()
        with pytest.raises(UnavailableError):
            await step_up.verify(s, actor, body, now)
    with pytest.raises(UnavailableError):
        await step_up.require(actor, "unlink", "some-token")
    await step_up.spend("auth:step_up:x")  # best effort; the token expires anyway
    with pytest.raises(ForbiddenError):
        await step_up.require(actor, "unlink", None)


async def test_phone_change_binding_fails_closed(
    sessions: Callable[[], AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    async with sessions() as s, s.begin():
        user = await make_user(s)  # no phone yet, so no step-up
    actor, now = Actor(user_id=user.id, session_id=uuid7(), roles=frozenset()), datetime.now(UTC)

    async def broken(*_: Any) -> None:
        raise RedisError("down")

    monkeypatch.setattr(phone_change, "set_json", broken)
    async with sessions() as s:
        with pytest.raises(UnavailableError):
            await phone_change.start(
                s, actor, PhoneStartIn(phone=PHONE), None, ip="1.2.3.4", now=now
            )
        redis_down()
        with pytest.raises(UnavailableError):
            await phone_change.confirm(
                s, actor, PhoneConfirmIn(challenge_id=uuid7(), code=TEST_CODE), now
            )

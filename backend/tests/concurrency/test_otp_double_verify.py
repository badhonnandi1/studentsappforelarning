"""Two parallel verifies of one challenge: one signs in, the other gets 410 (05 §E)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import make_sessionmaker
from app.core.errors import AppError
from app.core.security import crypto
from app.core.settings import Settings
from app.modules.auth.internal.models import DeviceSession
from app.modules.auth.internal.schemas.auth import DeviceInfo, OtpVerifyIn
from app.modules.auth.internal.services import otp_send, otp_verify
from tests.support.tokens import ensure_keys
from tests.support.users import make_user

pytestmark = pytest.mark.concurrency
PHONE = "+8801700000077"


async def test_one_challenge_signs_in_once(committed_engine: AsyncEngine, app_redis: Redis) -> None:
    del app_redis
    await crypto.init_crypto(Settings(_env_file=None))
    ensure_keys()
    sessions = make_sessionmaker(committed_engine)
    now = datetime.now(UTC)
    async with sessions() as session, session.begin():
        await make_user(session, phone=PHONE)
        challenge = await otp_send.issue(
            session, PHONE, "sign_in", ip="203.0.113.9", device_id="device-conc", now=now
        )
    device = DeviceInfo(device_id="device-conc", platform="web")
    body = OtpVerifyIn(challenge_id=challenge.id, code="123456", device=device)

    async def attempt() -> int:
        async with sessions() as session:
            try:
                await otp_verify.verify_sign_in(session, body, ip="203.0.113.9", now=now)
            except AppError as exc:
                return exc.status_code
            return 200

    results = sorted(await asyncio.gather(attempt(), attempt()))
    assert results == [200, 410]
    async with sessions() as session:
        live = select(func.count()).select_from(DeviceSession)
        assert (await session.execute(live)).scalar_one() == 1

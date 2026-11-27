"""Two parallel first sign-ins with one new social identity: one user, two sessions (05 §E)."""

from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import make_sessionmaker
from app.core.security import crypto
from app.core.settings import Settings
from app.modules.auth.internal.models import DeviceSession, ExternalIdentity, User
from app.modules.auth.internal.schemas.auth import DeviceInfo, SignInOut
from app.modules.auth.internal.schemas.social import SocialSignInIn
from app.modules.auth.internal.services import social_nonce, social_sign_in
from tests.support.social import install, token_for
from tests.support.tokens import ensure_keys

pytestmark = pytest.mark.concurrency


async def test_parallel_first_sign_ins_make_one_user(
    committed_engine: AsyncEngine, app_redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    del app_redis
    await crypto.init_crypto(Settings(_env_file=None))
    ensure_keys()
    fakes = install(monkeypatch)
    next(fakes)
    sessions, now = make_sessionmaker(committed_engine), datetime.now(UTC)

    async def attempt(device: str) -> SignInOut:
        nonce, _ = await social_nonce.issue("google", now)
        body = SocialSignInIn(
            token=token_for("google"), nonce=nonce, date_of_birth=date(2004, 4, 4),
            device=DeviceInfo(device_id=device, platform="android"),
        )  # fmt: skip
        async with sessions() as session:
            out = await social_sign_in.sign_in_with(
                session, "google", body, ip="198.51.100.4", now=now
            )
        assert isinstance(out, SignInOut)
        return out

    try:
        results = await asyncio.gather(attempt("device-race-1"), attempt("device-race-2"))
    finally:
        next(fakes, None)
    assert sorted(r.created for r in results) == [False, True]
    async with sessions() as session:
        for model, expected in ((User, 1), (ExternalIdentity, 1), (DeviceSession, 2)):
            count = select(func.count()).select_from(model)
            assert (await session.execute(count)).scalar_one() == expected, model

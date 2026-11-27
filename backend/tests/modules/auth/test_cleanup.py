"""``auth.sessions.purge_stale``: sessions idle for 90 days are revoked, not deleted."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.jobs import cleanup
from app.modules.auth.internal.models import DeviceSession, RefreshToken
from app.modules.nfr.contracts.jobs import JobContext
from tests.support.users import make_user

pytestmark = [pytest.mark.db, pytest.mark.integration]
NOW = datetime(2026, 11, 28, 3, 0, tzinfo=UTC)


def device_session(user_id: uuid.UUID, idle_days: int, device: str) -> DeviceSession:
    seen = NOW - timedelta(days=idle_days)
    return DeviceSession(
        id=uuid.uuid4(), user_id=user_id, device_id=device, platform="android",
        sign_in_method="otp", created_at=seen, last_seen_at=seen,
    )  # fmt: skip


async def test_purge_marks_idle_sessions_revoked(
    session: AsyncSession, sessions: Callable[[], AsyncSession]
) -> None:
    async with sessions() as s, s.begin():
        user = await make_user(s)
        stale, fresh = (
            device_session(user.id, 91, "d-stale"),
            device_session(user.id, 10, "d-fresh"),
        )
        s.add_all([stale, fresh])
        await s.flush()
        s.add(RefreshToken(id=uuid.uuid4(), session_id=stale.id, family_id=uuid.uuid4(),
                           token_hash=b"h" * 32, expires_at=NOW + timedelta(days=1)))  # fmt: skip
        ids = (stale.id, fresh.id)
    async with sessions() as s, s.begin():
        await cleanup.handle(JobContext(uuid.uuid4(), cleanup.KIND, "maintenance", 1, s, NOW), {})
    async with sessions() as s, s.begin():
        rows = {r.id: r for r in (await s.execute(select(DeviceSession))).scalars()}
        assert rows[ids[0]].revoke_reason == "inactive"
        assert rows[ids[1]].revoked_at is None
        token = (await s.execute(select(RefreshToken))).scalar_one()
        assert token.revoked_at == NOW
    del session

"""``identity.otp_challenges``: create, lock, count recent failures."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import OtpChallenge


async def insert(session: AsyncSession, row: OtpChallenge) -> OtpChallenge:
    session.add(row)
    await session.flush()
    return row


async def lock(session: AsyncSession, challenge_id: uuid.UUID) -> OtpChallenge | None:
    stmt = (
        select(OtpChallenge)
        .where(OtpChallenge.id == challenge_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def recent_failures(
    session: AsyncSession, phone_hash: bytes, now: datetime, window: timedelta
) -> int:
    """Wrong codes entered for this phone across every challenge in the window."""
    stmt = select(func.coalesce(func.sum(OtpChallenge.attempts), 0)).where(
        OtpChallenge.phone_hash == phone_hash, OtpChallenge.created_at >= now - window
    )
    return int((await session.execute(stmt)).scalar_one())

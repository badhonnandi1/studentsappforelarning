"""``identity.device_sessions`` and ``identity.refresh_tokens``."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import DeviceSession, RefreshToken


async def live_for_device(
    session: AsyncSession, user_id: uuid.UUID, device_id: str, audience: str
) -> DeviceSession | None:
    stmt = (
        select(DeviceSession)
        .where(
            DeviceSession.user_id == user_id,
            DeviceSession.device_id == device_id,
            DeviceSession.audience == audience,
            DeviceSession.revoked_at.is_(None),
        )
        .with_for_update()
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def live_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[DeviceSession]:
    """Newest activity first."""
    stmt = (
        select(DeviceSession)
        .where(DeviceSession.user_id == user_id, DeviceSession.revoked_at.is_(None))
        .order_by(DeviceSession.last_seen_at.desc(), DeviceSession.id.desc())
    )
    return list((await session.execute(stmt)).scalars())


async def get(
    session: AsyncSession, session_id: uuid.UUID, *, lock: bool = False
) -> DeviceSession | None:
    stmt = select(DeviceSession).where(DeviceSession.id == session_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def add(session: AsyncSession, row: DeviceSession | RefreshToken) -> None:
    session.add(row)
    await session.flush()


async def revoke_tokens(session: AsyncSession, session_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.session_id == session_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


async def revoke(session: AsyncSession, row: DeviceSession, reason: str, now: datetime) -> None:
    row.revoked_at, row.revoke_reason = now, reason
    await revoke_tokens(session, row.id, now)
    await session.flush()


async def token_by_hash(session: AsyncSession, token_hash: bytes) -> RefreshToken | None:
    stmt = (
        select(RefreshToken)
        .where(RefreshToken.token_hash == token_hash)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def revoke_family(session: AsyncSession, family_id: uuid.UUID, now: datetime) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )

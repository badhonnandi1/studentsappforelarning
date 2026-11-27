"""``identity.users``, default privacy settings and role grants: plain SQL helpers."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.modules.auth.internal.models import GuardianConsent, PrivacySetting, RoleGrant, User


async def get(session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False) -> User | None:
    stmt = select(User).where(User.id == user_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def by_phone_hash(session: AsyncSession, phone_hash: bytes) -> User | None:
    stmt = select(User).where(User.phone_hash == phone_hash)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create(session: AsyncSession, user: User, *, role: str) -> User:
    """Insert the user with private-by-default privacy settings and the base role grant."""
    session.add(user)
    await session.flush()
    session.add(PrivacySetting(user_id=user.id))
    session.add(RoleGrant(id=uuid7(), user_id=user.id, role_code=role))
    await session.flush()
    return user


async def active_roles(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    stmt = (
        select(RoleGrant.role_code)
        .where(RoleGrant.user_id == user_id, RoleGrant.revoked_at.is_(None))
        .distinct()
        .order_by(RoleGrant.role_code)
    )
    return list((await session.execute(stmt)).scalars())


async def has_active_guardian_consent(session: AsyncSession, user_id: uuid.UUID) -> bool:
    stmt = select(GuardianConsent.id).where(
        GuardianConsent.user_id == user_id, GuardianConsent.withdrawn_at.is_(None)
    )
    return (await session.execute(stmt.limit(1))).first() is not None


def touch(user: User, now: datetime) -> None:
    user.last_seen_at = now

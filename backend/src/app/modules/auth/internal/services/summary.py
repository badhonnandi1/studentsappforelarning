"""``UserSummary`` and ``TokenPair`` assembly (14 §2)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import DeviceSession, Profile, User
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import TokenPair, UserSummary
from app.modules.auth.internal.services.tokens import Issued
from app.shared.dhaka_date import age_on, dhaka_today

ADULT_AGE = 18


def is_minor(user: User, now: datetime) -> bool:
    if user.date_of_birth is None:
        return False
    return age_on(user.date_of_birth, dhaka_today(now)) < ADULT_AGE


async def needs_consent(session: AsyncSession, user: User, now: datetime) -> bool:
    """A minor without an active guardian consent (computed, not stored)."""
    if not is_minor(user, now):
        return False
    return not await users_repo.has_active_guardian_consent(session, user.id)


async def needs_profile(session: AsyncSession, user: User) -> bool:
    stmt = select(Profile.class_level).where(Profile.user_id == user.id)
    return (await session.execute(stmt)).scalar_one_or_none() is None


async def user_summary(
    session: AsyncSession, user: User, roles: list[str], now: datetime
) -> UserSummary:
    return UserSummary(
        id=user.id,
        display_name=user.display_name,
        first_name=user.first_name,
        is_minor=is_minor(user, now),
        roles=roles,
        needs_consent=await needs_consent(session, user, now),
        needs_profile=await needs_profile(session, user),
    )


def token_pair(issued: Issued, ds: DeviceSession, summary: UserSummary) -> TokenPair:
    return TokenPair(
        access_token=issued.access_token,
        access_expires_at=issued.access_expires_at,
        refresh_token=issued.refresh_token,
        refresh_expires_at=issued.refresh_expires_at,
        session_id=ds.id,
        user=summary,
    )

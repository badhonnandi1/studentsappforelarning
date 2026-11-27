"""``community.user_restrictions`` queries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.com.internal.models import UserRestriction


async def active_for_user(
    session: AsyncSession, user_id: uuid.UUID, now: datetime
) -> list[UserRestriction]:
    """Not lifted and not ended; rows that start later are included (callers check)."""
    stmt = select(UserRestriction).where(
        UserRestriction.user_id == user_id,
        UserRestriction.lifted_at.is_(None),
        or_(UserRestriction.ends_at.is_(None), UserRestriction.ends_at > now),
    )
    return list((await session.execute(stmt)).scalars())


async def get(session: AsyncSession, restriction_id: uuid.UUID) -> UserRestriction | None:
    return await session.get(UserRestriction, restriction_id, with_for_update=True)

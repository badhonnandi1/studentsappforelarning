"""Dormant account on a new device (R-25, SIM swap and recycled numbers).

No sign-in for 180 days and a device the account has never used: after the OTP, sign in with
a linked provider where one exists; otherwise the session is restricted for 72 h.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import User
from app.modules.auth.internal.repositories import identities as identities_repo
from app.modules.auth.internal.repositories import sessions as sessions_repo
from app.modules.auth.internal.schemas.step_up import SecondFactorOut

DORMANT_AFTER = timedelta(days=180)
RESTRICTED_FOR = timedelta(hours=72)


async def dormant_gate(
    session: AsyncSession, user: User, device_id: str, now: datetime
) -> SecondFactorOut | datetime | None:
    """Before ``start_session`` touches ``last_seen_at``. ``None`` means no extra rule."""
    if user.last_seen_at is None or user.last_seen_at > now - DORMANT_AFTER:
        return None
    if await sessions_repo.device_seen(session, user.id, device_id):
        return None
    linked = await identities_repo.active_for_user(session, user.id)
    if linked:
        return SecondFactorOut(providers=sorted({row.provider for row in linked}))
    return now + RESTRICTED_FOR

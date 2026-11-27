"""``consent_documents``, ``guardian_consents`` and ``privacy_settings`` queries."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import ConsentDocument, GuardianConsent, PrivacySetting


async def latest_version(session: AsyncSession, kind: str) -> str | None:
    stmt = (
        select(ConsentDocument.version)
        .where(ConsentDocument.kind == kind)
        .order_by(ConsentDocument.published_at.desc(), ConsentDocument.version.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def document(session: AsyncSession, version: str, lang: str) -> ConsentDocument | None:
    return await session.get(ConsentDocument, (version, lang))


async def active_consent(session: AsyncSession, user_id: uuid.UUID) -> GuardianConsent | None:
    stmt = (
        select(GuardianConsent)
        .where(GuardianConsent.user_id == user_id, GuardianConsent.withdrawn_at.is_(None))
        .order_by(GuardianConsent.granted_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def add_consent(session: AsyncSession, row: GuardianConsent) -> None:
    session.add(row)
    await session.flush()


async def privacy(
    session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False
) -> PrivacySetting:
    """The user's settings; a missing row (never expected) is created with the defaults."""
    row = await session.get(PrivacySetting, user_id, with_for_update=lock)
    if row is None:
        row = PrivacySetting(user_id=user_id, leaderboard_visible=True, profile_private=True)
        session.add(row)
        await session.flush()
    return row

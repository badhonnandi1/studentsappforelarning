"""``identity.external_identities``: lookup by ``(provider, subject)``, active links."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import ExternalIdentity, User


async def by_subject(
    session: AsyncSession, provider: str, subject: str, *, lock: bool = False
) -> ExternalIdentity | None:
    """Linked or unlinked: ``(provider, subject)`` is unique across both."""
    stmt = select(ExternalIdentity).where(
        ExternalIdentity.provider == provider, ExternalIdentity.provider_subject == subject
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return (await session.execute(stmt)).scalar_one_or_none()


async def active_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[ExternalIdentity]:
    stmt = (
        select(ExternalIdentity)
        .where(ExternalIdentity.user_id == user_id, ExternalIdentity.unlinked_at.is_(None))
        .order_by(ExternalIdentity.linked_at)
    )
    return list((await session.execute(stmt)).scalars())


async def active(
    session: AsyncSession, user_id: uuid.UUID, provider: str, *, lock: bool = False
) -> ExternalIdentity | None:
    stmt = select(ExternalIdentity).where(
        ExternalIdentity.user_id == user_id,
        ExternalIdentity.provider == provider,
        ExternalIdentity.unlinked_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await session.execute(stmt)).scalar_one_or_none()


async def user_by_email(session: AsyncSession, email_hash: bytes) -> User | None:
    """``users.email_hash`` is unique; the caller checks ``email_verified_at``."""
    stmt = select(User).where(User.email_hash == email_hash)
    return (await session.execute(stmt)).scalar_one_or_none()

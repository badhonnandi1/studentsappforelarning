"""``GET /v1/me`` and ``PATCH /v1/me``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security.actor import Actor
from app.core.security.crypto import decrypt_field
from app.modules import com
from app.modules.auth.internal.models import ExternalIdentity, User
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.me import ConsentState, IdentityItem, MeOut, MePatchIn
from app.modules.auth.internal.services import summary
from app.shared.bd_phone import mask_bd_phone

PHONE_CONTEXT = "identity.users.phone"


async def _me(session: AsyncSession, user: User, now: datetime) -> MeOut:
    roles = await users_repo.active_roles(session, user.id)
    base = await summary.user_summary(session, user, roles, now)
    stmt = select(ExternalIdentity).where(
        ExternalIdentity.user_id == user.id, ExternalIdentity.unlinked_at.is_(None)
    )
    identities = [
        IdentityItem(provider=i.provider, linked_at=i.linked_at)
        for i in (await session.execute(stmt.order_by(ExternalIdentity.linked_at))).scalars()
    ]
    phone = decrypt_field(user.phone_enc, PHONE_CONTEXT) if user.phone_enc else None
    if not base.is_minor:
        consent = ConsentState(required=False, status="not_required")
    else:
        consent = ConsentState(required=True, status="missing" if base.needs_consent else "granted")
    return MeOut(
        **base.model_dump(),
        phone_masked=mask_bd_phone(phone) if phone else None,
        identities=identities,
        consent=consent,
    )


async def get_me(session: AsyncSession, actor: Actor, now: datetime) -> MeOut:
    async with session.begin():
        return await _me(session, await summary.signed_in_user(session, actor), now)


async def patch_me(session: AsyncSession, actor: Actor, body: MePatchIn, now: datetime) -> MeOut:
    """A new display name goes through COM moderation first (a block is ``422``)."""
    if body.display_name is not None:
        if await com.is_restricted(session, actor.user_id, "profile", now):
            raise ForbiddenError("Your account cannot change its display name", code="restricted")
        await com.ensure_allowed(
            session, body.display_name, "display_name", str(actor.user_id), user_id=actor.user_id
        )
    async with session.begin():
        user = await summary.signed_in_user(session, actor, lock=True)
        for name, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
            setattr(user, name, value)
        await session.flush()
        return await _me(session, user, now)

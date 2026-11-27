"""Linked identities from a signed-in session (05 §C.5): list, link, unlink.

Unlinking needs a verified phone, an unrestricted session and a step-up token, and never
removes the last sign-in method. Unlinked rows are kept (``unlinked_at``, ``unlink_reason``).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.security.actor import Actor
from app.core.security.crypto import decrypt_field
from app.modules import ops
from app.modules.auth.internal.models import ExternalIdentity
from app.modules.auth.internal.repositories import identities as repo
from app.modules.auth.internal.schemas.social import IdentitiesOut, IdentityOut, LinkIn
from app.modules.auth.internal.services import accounts, social_sign_in, step_up, summary


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def identity_out(row: ExternalIdentity) -> IdentityOut:
    email = decrypt_field(row.email_enc, accounts.IDENTITY_EMAIL_CONTEXT) if row.email_enc else None
    return IdentityOut(
        provider=row.provider,
        display_name=row.display_name,
        email_masked=mask_email(email) if email else None,
        linked_at=row.linked_at,
        last_login_at=row.last_login_at,
    )


async def list_identities(session: AsyncSession, actor: Actor) -> IdentitiesOut:
    user = await summary.signed_in_user(session, actor)
    rows = await repo.active_for_user(session, user.id)
    await session.commit()
    return IdentitiesOut(
        items=[identity_out(r) for r in rows], phone_verified=user.phone_hash is not None
    )


async def link(
    session: AsyncSession, actor: Actor, provider: str, body: LinkIn, now: datetime
) -> IdentityOut:
    ident = await social_sign_in.verified(provider, body.token, body.nonce)
    async with session.begin():
        user = await summary.signed_in_user(session, actor, lock=True)
        accounts.age_gate(provider, user.date_of_birth, now)
        row = await repo.by_subject(session, provider, ident.subject, lock=True)
        if row is not None and row.unlinked_at is None and row.user_id != user.id:
            raise ConflictError("This account is linked to someone else", code="identity_in_use")
        if await repo.active(session, user.id, provider) is not None:
            raise ConflictError("You already have this sign-in method linked")
        row = await accounts.attach_identity(session, user, ident, row, now)
        target = ops.AuditTarget(type="user", id=str(user.id))
        async with ops.audited(session, actor, "auth.identity.link", target, now=now) as audit:
            audit.after = {"provider": provider}
        return identity_out(row)


async def unlink(
    session: AsyncSession, actor: Actor, provider: str, token: str | None, now: datetime
) -> None:
    async with session.begin():
        step_up.require_phone(await summary.signed_in_user(session, actor))
        await step_up.ensure_unrestricted(session, actor, now)
    key = await step_up.require(actor, "unlink", token)
    async with session.begin():
        user = await summary.signed_in_user(session, actor, lock=True)
        row = await repo.active(session, user.id, provider, lock=True)
        if row is None:
            raise NotFoundError("This sign-in method is not linked")
        methods = (user.phone_hash is not None) + len(await repo.active_for_user(session, user.id))
        if (
            methods <= 1
        ):  # pragma: no cover - a verified phone is required above (B8 adds passwords)
            raise ConflictError("Keep at least one way to sign in", code="last_sign_in_method")
        row.unlinked_at, row.unlink_reason = now, "user"
        target = ops.AuditTarget(type="user", id=str(user.id))
        async with ops.audited(session, actor, "auth.identity.unlink", target, now=now) as audit:
            audit.after = {"provider": provider}
    await step_up.spend(key)

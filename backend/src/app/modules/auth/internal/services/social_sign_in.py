"""Social sign-in (05 §C.5): nonce → provider verify → identity lookup → linking rules →
DOB and age gate before creation (R-24) → the shared ``sign_in``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.security.hashing import keyed_hash
from app.modules import ops
from app.modules.auth.contracts.events import SignInMethod
from app.modules.auth.internal.models import User
from app.modules.auth.internal.providers import registry
from app.modules.auth.internal.providers.base import VerifiedIdentity
from app.modules.auth.internal.repositories import identities as identities_repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import NeedsProfileOut, SignInOut
from app.modules.auth.internal.schemas.social import SocialSignInIn
from app.modules.auth.internal.services import accounts, pending_signup, sign_in, social_nonce


async def verified(provider_name: str, token: str, nonce: str) -> VerifiedIdentity:
    """Steps 1–3: the provider must be enabled, the nonce ours and unused, the token valid."""
    provider = registry.get(provider_name)
    await social_nonce.consume(nonce, provider_name)
    return await provider.verify(token, nonce)


async def _existing_user(
    session: AsyncSession, ident: VerifiedIdentity, now: datetime
) -> tuple[User | None, bool]:
    """Steps 4–5 and 9. Returns ``(user, autolinked)``."""
    row = await identities_repo.by_subject(session, ident.provider, ident.subject, lock=True)
    if row is not None and row.unlinked_at is None:
        user = await users_repo.get(session, row.user_id, lock=True)
        row.last_login_at = now
        return user, False
    if ident.provider != "google" or not ident.email_verified or not ident.email:
        return None, False  # Facebook never auto-links by email
    user = await identities_repo.user_by_email(session, keyed_hash(ident.email, "email"))
    if user is None or user.email_verified_at is None:
        return None, False
    sign_in.check_status(user)
    if await identities_repo.active(session, user.id, "google") is not None:
        return None, False  # that account already has another Google identity
    await accounts.attach_identity(session, user, ident, row, now)
    target = ops.AuditTarget(type="user", id=str(user.id))
    who = ops.AuditActor(kind="user", user_id=user.id, roles=())
    async with ops.audited(session, who, "auth.identity_autolinked", target, now=now) as audit:
        audit.after = {"provider": ident.provider}
    return user, True


async def sign_in_with(
    session: AsyncSession, provider_name: str, body: SocialSignInIn, *, ip: str, now: datetime
) -> SignInOut | NeedsProfileOut:
    if body.date_of_birth is not None:
        pending_signup.check_dob(body.date_of_birth, now)
    ident = await verified(provider_name, body.token, body.nonce)
    started: sign_in.Started | None = None
    linked = created = False
    async with session.begin():
        user, linked = await _existing_user(session, ident, now)
        if user is None:
            if body.date_of_birth is None:  # step 6: nothing is created
                token = await pending_signup.create_for_identity(ident, body.device)
                return NeedsProfileOut(pending_signup_token=token)
            user = await accounts.create_social_account(
                session, ident, dob=body.date_of_birth, display_name=None, now=now
            )
            created = True
        if user is None:  # pragma: no cover - an identity row always has its user
            raise ForbiddenError("This account cannot sign in")
        accounts.age_gate(ident.provider, user.date_of_birth, now)
        method: SignInMethod = "google" if ident.provider == "google" else "facebook"
        started = await sign_in.start_session(
            session, user, method, body.device, ip=ip, now=now, created=created
        )
    await sign_in.after_commit(started)
    return SignInOut(**started.pair.model_dump(), linked=linked, created=created)

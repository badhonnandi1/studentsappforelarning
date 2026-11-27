"""Account creation shared by phone and social sign-up, and identity attachment (R-24).

The caller has the date of birth before anything is created. ``kill.registrations`` refuses
new accounts (OPS-07). Facebook under 13 is refused before creation (05 §C.4).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError
from app.core.ids import uuid7
from app.core.security.crypto import decrypt_field, encrypt_field
from app.core.security.hashing import keyed_hash
from app.modules import nfr
from app.modules.auth.internal.models import ExternalIdentity, User
from app.modules.auth.internal.permissions import DEFAULT_ROLE
from app.modules.auth.internal.providers.base import VerifiedIdentity
from app.modules.auth.internal.repositories import identities as identities_repo
from app.modules.auth.internal.repositories import users as users_repo
from app.shared.dhaka_date import age_on, dhaka_today

USER_PHONE_CONTEXT = "identity.users.phone"
USER_EMAIL_CONTEXT = "identity.users.email"
IDENTITY_EMAIL_CONTEXT = "identity.external_identities.email"
FACEBOOK_MIN_AGE = 13


def phone_of(user: User) -> str:
    """Only for an account with a phone (check ``phone_hash`` first)."""
    return decrypt_field(user.phone_enc or b"", USER_PHONE_CONTEXT)


def age_gate(provider: str, dob: date | None, now: datetime) -> None:
    too_young = dob is not None and age_on(dob, dhaka_today(now)) < FACEBOOK_MIN_AGE
    if provider == "facebook" and too_young:
        raise ForbiddenError("Facebook sign-in is for 13 and over", code="age_restricted")


async def create_user(
    session: AsyncSession,
    *,
    dob: date,
    display_name: str | None,
    now: datetime,
    phone: str | None = None,
    verified_email: str | None = None,
) -> User:
    await nfr.require_enabled(session, "registrations")
    user = User(
        id=uuid7(),
        date_of_birth=dob,
        display_name=display_name,
        status="active",
        locale="bn",
        created_at=now,
    )
    if phone is not None:
        user.phone_hash = keyed_hash(phone, "phone")
        user.phone_enc = encrypt_field(phone, USER_PHONE_CONTEXT)
    if verified_email is not None:
        user.email_hash = keyed_hash(verified_email, "email")
        user.email_enc = encrypt_field(verified_email, USER_EMAIL_CONTEXT)
        user.email_verified_at = now
    return await users_repo.create(session, user, role=DEFAULT_ROLE)


async def attach_identity(
    session: AsyncSession,
    user: User,
    ident: VerifiedIdentity,
    row: ExternalIdentity | None,
    now: datetime,
) -> ExternalIdentity:
    """Link ``ident`` to ``user``. An unlinked row for the same subject is reused, because
    ``(provider, subject)`` stays unique after unlinking."""
    if row is None:
        row = ExternalIdentity(id=uuid7(), provider=ident.provider, provider_subject=ident.subject)
        session.add(row)
    row.user_id, row.linked_at, row.last_login_at = user.id, now, now
    row.unlinked_at, row.unlink_reason = None, None
    row.display_name, row.email_verified = ident.name, ident.email_verified
    row.email_enc = encrypt_field(ident.email, IDENTITY_EMAIL_CONTEXT) if ident.email else None
    row.email_hash = keyed_hash(ident.email, "email") if ident.email else None
    await session.flush()
    return row


class RegistrationRaceError(ConflictError):
    """A parallel first sign-in with the same identity committed first (05 §E)."""

    def __init__(self) -> None:
        super().__init__("This account is already registered; sign in instead")


async def create_social_account(
    session: AsyncSession,
    ident: VerifiedIdentity,
    *,
    dob: date,
    display_name: str | None,
    now: datetime,
) -> User:
    """A new user for a provider identity. A verified Google email is kept on the user unless
    another account already has it (it is never moved)."""
    age_gate(ident.provider, dob, now)
    row = await identities_repo.by_subject(session, ident.provider, ident.subject, lock=True)
    if row is not None and row.unlinked_at is None:
        raise ConflictError("This account is already registered; sign in instead")
    email = ident.email if ident.provider == "google" and ident.email_verified else None
    if email and await identities_repo.user_by_email(session, keyed_hash(email, "email")):
        email = None
    try:
        async with session.begin_nested():
            user = await create_user(
                session, dob=dob, display_name=display_name, now=now, verified_email=email
            )
            await attach_identity(session, user, ident, row, now)
            await session.flush()
    except IntegrityError:
        winner = await identities_repo.by_subject(session, ident.provider, ident.subject)
        if winner is None or winner.unlinked_at is not None:
            raise
        raise RegistrationRaceError() from None
    return user

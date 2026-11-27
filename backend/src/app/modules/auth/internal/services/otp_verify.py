"""Check an OTP: row lock, expiry, attempts ≤ 5, constant-time compare, consume (05 §C.4).

A wrong code increments ``attempts`` and that update commits before the 401 is raised, so the
limit holds across requests. Sign-in by OTP consumes the challenge and starts the session in one
transaction; a new number gets a pending sign-up token instead of an account (R-24).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import GoneError, TooManyRequestsError, UnauthorizedError
from app.core.security.crypto import decrypt_field
from app.core.security.hashing import constant_time_equal, otp_hash
from app.modules.auth.internal.models import OtpChallenge
from app.modules.auth.internal.repositories import otp as repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import NeedsProfileOut, OtpVerifyIn, SignInOut
from app.modules.auth.internal.services import pending_signup, sign_in
from app.modules.auth.internal.services.otp_send import PHONE_CONTEXT

MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class WrongCode:
    attempts_left: int

    def error(self) -> UnauthorizedError:
        return UnauthorizedError(
            "That code is not right",
            code="invalid_code",
            details={"attempts_left": self.attempts_left},
        )


async def consume(
    session: AsyncSession, challenge_id: uuid.UUID, code: str, purpose: str, now: datetime
) -> OtpChallenge | WrongCode:
    """Inside the caller's transaction. Returns ``WrongCode`` (the caller commits, then raises)."""
    row = await repo.lock(session, challenge_id)
    if row is None or row.purpose != purpose:
        raise UnauthorizedError("That code is not right", code="invalid_code")
    if row.consumed_at is not None or row.expires_at <= now:
        raise GoneError("This code has expired; ask for a new one")
    if row.attempts >= MAX_ATTEMPTS:
        retry = max(1, int((row.expires_at - now).total_seconds()))
        raise TooManyRequestsError("Too many wrong codes; ask for a new one", retry_after=retry)
    if not constant_time_equal(row.code_hash, otp_hash(code, str(row.id))):
        row.attempts += 1
        await session.flush()
        return WrongCode(MAX_ATTEMPTS - row.attempts)
    row.consumed_at = now
    await session.flush()
    return row


def phone_of(row: OtpChallenge) -> str:
    return decrypt_field(row.phone_enc, PHONE_CONTEXT)


async def verify_sign_in(
    session: AsyncSession, body: OtpVerifyIn, *, ip: str, now: datetime
) -> SignInOut | NeedsProfileOut:
    started: sign_in.Started | None = None
    result: SignInOut | NeedsProfileOut | None = None
    async with session.begin():
        outcome = await consume(session, body.challenge_id, body.code, "sign_in", now)
        if not isinstance(outcome, WrongCode):
            user = await users_repo.by_phone_hash(session, outcome.phone_hash)
            if user is None:
                token = await pending_signup.create_for_phone(phone_of(outcome), body.device)
                result = NeedsProfileOut(pending_signup_token=token)
            else:
                started = await sign_in.start_session(
                    session, user, "otp", body.device, ip=ip, now=now
                )
                result = SignInOut(**started.pair.model_dump())
    if isinstance(outcome, WrongCode):
        raise outcome.error()
    if started is not None:
        await sign_in.after_commit(started)
    if result is None:  # pragma: no cover - every branch above sets it
        raise RuntimeError("OTP verify produced no result")
    return result

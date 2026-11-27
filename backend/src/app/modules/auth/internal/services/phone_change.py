"""``POST /v1/me/phone`` in two steps (05 §D, R-25).

Start: a step-up token when the account already has a phone, an unrestricted session, and a
number no other account uses; an OTP (``purpose = phone_change``) goes to the new number and
the challenge is bound to the caller in Redis. Confirm: the code, the same checks again, the
new number stored encrypted with its keyed hash, and an audit row, in one transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Final

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, UnauthorizedError, UnavailableError, ValidationAppError
from app.core.redis import get_json, set_json
from app.core.security.actor import Actor
from app.core.security.crypto import encrypt_field
from app.core.security.hashing import keyed_hash
from app.modules import ops
from app.modules.auth.internal.models import OtpChallenge, User
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.step_up import PhoneConfirmIn, PhoneOut, PhoneStartIn
from app.modules.auth.internal.services import accounts, otp_send, otp_verify, step_up, summary
from app.modules.auth.internal.services.otp_verify import WrongCode
from app.shared.bd_phone import mask_bd_phone

PURPOSE: Final = "phone_change"
BINDING_TTL = otp_send.CODE_TTL + timedelta(minutes=10)


def binding_key(challenge_id: uuid.UUID) -> str:
    return f"auth:phone_change:{challenge_id}"


async def _check_number(session: AsyncSession, user: User, phone_hash: bytes) -> None:
    if user.phone_hash == phone_hash:
        raise ValidationAppError("This is already your number", code="same_phone")
    if await users_repo.by_phone_hash(session, phone_hash) is not None:
        raise ConflictError("This number belongs to another account; contact support")


async def start(
    session: AsyncSession,
    actor: Actor,
    body: PhoneStartIn,
    token: str | None,
    *,
    ip: str,
    now: datetime,
) -> OtpChallenge:
    phone = otp_send.parse_phone(body.phone)
    phone_hash = keyed_hash(phone, "phone")
    async with session.begin():
        user = await summary.signed_in_user(session, actor)
        has_phone = user.phone_hash is not None
        if has_phone:  # adding a first number needs no step-up: there is nothing to confirm with
            await step_up.ensure_unrestricted(session, actor, now)
        await _check_number(session, user, phone_hash)
    key = await step_up.require(actor, PURPOSE, token) if has_phone else None
    await otp_send.enforce_client_limits(ip=ip, device_id=None)
    await otp_send.enforce_phone_limit(phone_hash)
    async with session.begin():
        row = await otp_send.issue(session, phone, PURPOSE, ip=ip, device_id=None, now=now)
        try:
            ttl = int(BINDING_TTL.total_seconds())
            await set_json(binding_key(row.id), {"user_id": str(actor.user_id)}, ttl)
        except (RedisError, OSError) as exc:
            raise UnavailableError("Try again in a moment") from exc
    if key is not None:
        await step_up.spend(key)
    return row


async def confirm(
    session: AsyncSession, actor: Actor, body: PhoneConfirmIn, now: datetime
) -> PhoneOut:
    try:
        bound = await get_json(binding_key(body.challenge_id))
    except (RedisError, OSError) as exc:
        raise UnavailableError("Try again in a moment") from exc
    if not isinstance(bound, dict) or bound.get("user_id") != str(actor.user_id):
        raise UnauthorizedError("That code is not right", code="invalid_code")
    result: PhoneOut | None = None
    async with session.begin():
        user = await summary.signed_in_user(session, actor, lock=True)
        outcome = await otp_verify.consume(session, body.challenge_id, body.code, PURPOSE, now)
        if not isinstance(outcome, WrongCode):
            await _check_number(session, user, outcome.phone_hash)
            phone = otp_verify.phone_of(outcome)
            had_phone = user.phone_hash is not None
            user.phone_hash = outcome.phone_hash
            user.phone_enc = encrypt_field(phone, accounts.USER_PHONE_CONTEXT)
            target = ops.AuditTarget(type="user", id=str(user.id))
            async with ops.audited(session, actor, "auth.phone.change", target, now=now) as audit:
                audit.after = {"had_phone": had_phone}
            result = PhoneOut(phone_masked=mask_bd_phone(phone))
    if isinstance(outcome, WrongCode):
        raise outcome.error()
    if result is None:  # pragma: no cover - every branch above sets it
        raise RuntimeError("phone change produced no result")
    return result

"""Step-up OTP and the dormant and new-device rules (R-25).

The OTP goes to the account's verified phone (``purpose = step_up``, 10 minutes). A challenge
belongs to the caller when its phone hash is the caller's (numbers are unique). The token is
bound to the user, the session and the action, stored only as a hash, and spent after the
action commits. Restricted sessions (``dormant.py``) cannot use it for unlink or phone change.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, UnauthorizedError, UnavailableError
from app.core.redis import get_redis
from app.core.security.actor import Actor
from app.modules.auth.internal.models import OtpChallenge, User
from app.modules.auth.internal.repositories import sessions as sessions_repo
from app.modules.auth.internal.schemas.step_up import StepUpIn, StepUpOut
from app.modules.auth.internal.services import accounts, otp_send, otp_verify, summary
from app.modules.auth.internal.services.otp_verify import WrongCode

TOKEN_TTL = timedelta(minutes=10)
UNAVAILABLE = "Verification is unavailable; try again shortly"


def token_key(token: str) -> str:
    return f"auth:step_up:{hashlib.sha256(token.encode()).hexdigest()}"


def require_phone(user: User) -> bytes:
    if user.phone_hash is None:
        raise ForbiddenError("Add a phone number to your account first", code="phone_required")
    return user.phone_hash


async def send(session: AsyncSession, actor: Actor, *, ip: str, now: datetime) -> OtpChallenge:
    async with session.begin():
        user = await summary.signed_in_user(session, actor)
        phone_hash = require_phone(user)
        phone = accounts.phone_of(user)
    await otp_send.enforce_client_limits(ip=ip, device_id=None)
    await otp_send.enforce_phone_limit(phone_hash)
    async with session.begin():
        return await otp_send.issue(session, phone, "step_up", ip=ip, device_id=None, now=now)


async def verify(session: AsyncSession, actor: Actor, body: StepUpIn, now: datetime) -> StepUpOut:
    async with session.begin():
        user = await summary.signed_in_user(session, actor)
        phone_hash = require_phone(user)
        outcome = await otp_verify.consume(
            session, body.otp_challenge_id, body.code, "step_up", now
        )
        if not isinstance(outcome, WrongCode) and outcome.phone_hash != phone_hash:
            raise UnauthorizedError("That code is not right", code="invalid_code")
    if isinstance(outcome, WrongCode):
        raise outcome.error()
    token = secrets.token_urlsafe(32)
    bound = {
        "user_id": str(actor.user_id),
        "session_id": str(actor.session_id),
        "action": body.action,
    }
    try:
        await get_redis().set(
            token_key(token), json.dumps(bound), ex=int(TOKEN_TTL.total_seconds())
        )
    except (RedisError, OSError) as exc:
        raise UnavailableError(UNAVAILABLE) from exc
    return StepUpOut(step_up_token=token, expires_at=now + TOKEN_TTL)


async def require(actor: Actor, action: str, token: str | None) -> str:
    """Check ``X-Step-Up-Token``; return the key to ``spend`` after the action commits."""
    if not token:
        raise ForbiddenError("Confirm with a code sent to your phone", code="step_up_required")
    key = token_key(token)
    try:
        raw = await get_redis().get(key)
    except (RedisError, OSError) as exc:
        raise UnavailableError(UNAVAILABLE) from exc
    bound = json.loads(raw) if raw else {}
    wanted = {"user_id": str(actor.user_id), "session_id": str(actor.session_id), "action": action}
    if bound != wanted:
        raise ForbiddenError("Confirm with a code sent to your phone", code="step_up_required")
    return key


async def spend(key: str) -> None:
    try:
        await get_redis().delete(key)
    except (RedisError, OSError):  # it expires within 10 minutes anyway
        return


async def ensure_unrestricted(session: AsyncSession, actor: Actor, now: datetime) -> None:
    """Restricted sessions cannot change the phone, unlink or pay (R-25)."""
    ds = await sessions_repo.get(session, actor.session_id)
    if ds is not None and ds.restricted_until is not None and ds.restricted_until > now:
        raise ForbiddenError(
            "This is not allowed on a new device yet", code="restricted_session",
            details={"restricted_until": ds.restricted_until.isoformat()},
        )  # fmt: skip

"""Pending sign-up (R-24): no ``users`` row exists until the date of birth is known.

The token is single use (``GETDEL``), valid 15 minutes, and bound to the verified phone (or, from
step 10, the provider identity). The Redis value holds the phone encrypted, never in plain text.
"""

from __future__ import annotations

import base64
import json
import secrets
from datetime import date, datetime
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, GoneError, UnavailableError, ValidationAppError
from app.core.ids import uuid7
from app.core.redis import get_redis
from app.core.security.crypto import decrypt_field, encrypt_field
from app.core.security.hashing import keyed_hash
from app.modules.auth.internal.models import User
from app.modules.auth.internal.permissions import DEFAULT_ROLE
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import DeviceInfo, SignUpCompleteIn, TokenPair
from app.modules.auth.internal.services import sign_in
from app.shared.dhaka_date import dhaka_today

TTL_S = 15 * 60
CONTEXT = "auth.pending_signup.phone"
USER_PHONE_CONTEXT = "identity.users.phone"
EARLIEST_DOB = date(1900, 1, 1)


def key(token: str) -> str:
    return f"auth:pending_signup:{token}"


async def _store(data: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    try:
        await get_redis().set(key(token), json.dumps(data), ex=TTL_S)
    except (RedisError, OSError) as exc:
        raise UnavailableError("Sign-up is unavailable; try again shortly") from exc
    return token


async def create_for_phone(phone: str, device: DeviceInfo) -> str:
    blob = base64.b64encode(encrypt_field(phone, CONTEXT)).decode()
    return await _store({"method": "otp", "phone_enc": blob, "device": device.model_dump()})


async def take(token: str) -> dict[str, Any] | None:
    try:
        raw = await get_redis().getdel(key(token))
    except (RedisError, OSError) as exc:
        raise UnavailableError("Sign-up is unavailable; try again shortly") from exc
    return json.loads(raw) if raw else None


def check_dob(dob: date, now: datetime) -> None:
    if not EARLIEST_DOB <= dob < dhaka_today(now):
        raise ValidationAppError(
            "Enter a valid date of birth", details={"date_of_birth": "invalid"}
        )


async def complete(
    session: AsyncSession, body: SignUpCompleteIn, *, ip: str, now: datetime
) -> TokenPair:
    check_dob(body.date_of_birth, now)  # before the token is spent
    data = await take(body.pending_signup_token)
    if data is None or data.get("method") != "otp":
        raise GoneError("This sign-up has expired; start again")
    phone = decrypt_field(base64.b64decode(data["phone_enc"]), CONTEXT)
    device = DeviceInfo.model_validate(data["device"])
    phone_hash = keyed_hash(phone, "phone")
    async with session.begin():
        if await users_repo.by_phone_hash(session, phone_hash) is not None:
            raise ConflictError("This number already has an account; sign in instead")
        user = User(
            id=uuid7(),
            phone_hash=phone_hash,
            phone_enc=encrypt_field(phone, USER_PHONE_CONTEXT),
            date_of_birth=body.date_of_birth,
            display_name=body.display_name,
            status="active",
            locale="bn",
        )
        await users_repo.create(session, user, role=DEFAULT_ROLE)
        started = await sign_in.start_session(
            session, user, "otp", device, ip=ip, now=now, created=True
        )
    await sign_in.after_commit(started)
    return started.pair

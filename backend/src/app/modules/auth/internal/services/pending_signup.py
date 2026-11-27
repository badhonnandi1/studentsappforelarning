"""Pending sign-up (R-24): no ``users`` row exists until the date of birth is known.

The token is single use (``GETDEL``), valid 15 minutes, and bound to the verified phone or the
verified provider identity. Redis holds them encrypted, never in plain text.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import secrets
from datetime import date, datetime
from typing import Any

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, GoneError, UnavailableError, ValidationAppError
from app.core.redis import get_redis
from app.core.security.crypto import decrypt_field, encrypt_field
from app.core.security.hashing import keyed_hash
from app.modules import com
from app.modules.auth.contracts.events import SignInMethod
from app.modules.auth.internal.models import User
from app.modules.auth.internal.providers.base import VerifiedIdentity
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import DeviceInfo, SignUpCompleteIn, TokenPair
from app.modules.auth.internal.services import accounts, sign_in
from app.shared.dhaka_date import dhaka_today

TTL_S = 15 * 60
CONTEXT = "auth.pending_signup.phone"
IDENTITY_CONTEXT = "auth.pending_signup.identity"
EARLIEST_DOB = date(1900, 1, 1)
SOCIAL: tuple[SignInMethod, ...] = ("google", "facebook")


def key(token: str) -> str:
    return f"auth:pending_signup:{token}"


def _seal(value: str, context: str) -> str:
    return base64.b64encode(encrypt_field(value, context)).decode()


def _open(blob: str, context: str) -> str:
    return decrypt_field(base64.b64decode(blob), context)


async def _store(data: dict[str, Any]) -> str:
    token = secrets.token_urlsafe(32)
    try:
        await get_redis().set(key(token), json.dumps(data), ex=TTL_S)
    except (RedisError, OSError) as exc:
        raise UnavailableError("Sign-up is unavailable; try again shortly") from exc
    return token


async def create_for_phone(phone: str, device: DeviceInfo) -> str:
    return await _store(
        {"method": "otp", "phone_enc": _seal(phone, CONTEXT), "device": device.model_dump()}
    )


async def create_for_identity(ident: VerifiedIdentity, device: DeviceInfo) -> str:
    sealed = _seal(json.dumps(dataclasses.asdict(ident)), IDENTITY_CONTEXT)
    return await _store(
        {"method": ident.provider, "identity_enc": sealed, "device": device.model_dump()}
    )


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


async def _phone_user(
    session: AsyncSession, data: dict[str, Any], body: SignUpCompleteIn, now: datetime
) -> User:
    phone = _open(data["phone_enc"], CONTEXT)
    if await users_repo.by_phone_hash(session, keyed_hash(phone, "phone")) is not None:
        raise ConflictError("This number already has an account; sign in instead")
    return await accounts.create_user(
        session, dob=body.date_of_birth, display_name=body.display_name, now=now, phone=phone
    )


async def complete(
    session: AsyncSession, body: SignUpCompleteIn, *, ip: str, now: datetime
) -> TokenPair:
    check_dob(body.date_of_birth, now)  # before the token is spent
    if body.display_name:
        await com.ensure_allowed(session, body.display_name, "display_name")
    data = await take(body.pending_signup_token)
    method = data.get("method") if data else None
    if data is None or (method != "otp" and method not in SOCIAL):
        raise GoneError("This sign-up has expired; start again")
    device = DeviceInfo.model_validate(data["device"])
    async with session.begin():
        if method == "otp":
            user = await _phone_user(session, data, body, now)
        else:
            ident = VerifiedIdentity(**json.loads(_open(data["identity_enc"], IDENTITY_CONTEXT)))
            user = await accounts.create_social_account(
                session, ident, dob=body.date_of_birth, display_name=body.display_name, now=now
            )
        started = await sign_in.start_session(
            session, user, method, device, ip=ip, now=now, created=True
        )
    await sign_in.after_commit(started)
    return started.pair

"""Issue OTP challenges: phone rules, T-otp limits, CAPTCHA after failures (05 §C.4).

The response never says whether the number has an account; only a suspended number is refused.
Codes are HMAC-hashed with the challenge id. Test numbers (R-31) get the fixed test code only
when the settings allow it; the SMS job never sends to them.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.errors import ForbiddenError, ValidationAppError
from app.core.ids import uuid7
from app.core.security.crypto import encrypt_field
from app.core.security.hashing import keyed_hash, otp_hash
from app.core.settings import TEST_PHONE_FIRST, TEST_PHONE_LAST, get_settings
from app.modules import plan
from app.modules.auth.internal.models import OtpChallenge
from app.modules.auth.internal.providers.captcha import require_challenge
from app.modules.auth.internal.repositories import otp as repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import OtpSendIn
from app.shared.bd_phone import normalize_bd_phone

OtpPurpose = Literal["sign_in", "guardian_consent", "phone_change", "step_up"]
CODE_TTL = timedelta(minutes=5)
STEP_UP_TTL = timedelta(minutes=10)
RESEND_AFTER_S = 60
FAILURE_WINDOW = timedelta(hours=1)
FAILURES_BEFORE_CHALLENGE = 3
PHONE_CONTEXT = "identity.otp_challenges.phone"
TEMPLATES: dict[str, tuple[str, plan.Purpose]] = {
    "sign_in": ("auth.otp", "otp"),
    "phone_change": ("auth.otp", "otp"),
    "step_up": ("auth.otp", "otp"),
    "guardian_consent": ("auth.guardian_otp", "guardian_otp"),
}


def parse_phone(raw: str) -> str:
    phone = normalize_bd_phone(raw)
    if phone is None:
        raise ValidationAppError("Enter a Bangladesh mobile number", code="invalid_phone")
    return phone


def is_test_phone(phone: str) -> bool:
    return TEST_PHONE_FIRST <= phone <= TEST_PHONE_LAST


def new_code(phone: str) -> str:
    settings = get_settings()
    if is_test_phone(phone) and settings.test_otp_allowed:
        return settings.test_phone_otp
    return f"{secrets.randbelow(10**6):06d}"


async def enforce_client_limits(*, ip: str, device_id: str | None) -> None:
    """T-otp per IP and device. Fails closed when Redis is down. Keys are hashed."""
    keys = {"ip": keyed_hash(ip, "ip").hex()}
    if device_id:
        keys["device"] = keyed_hash(device_id, "device").hex()
    await ratelimit.enforce("otp_ip", keys)


async def enforce_phone_limit(phone_hash: bytes) -> None:
    """T-otp per phone (3 per 15 min, 5 per day), after the CAPTCHA check so a refused
    request does not spend the number's quota."""
    await ratelimit.enforce("otp_phone", {"phone": phone_hash.hex()})


async def check_challenge(
    session: AsyncSession, phone_hash: bytes, token: str | None, *, ip: str, now: datetime
) -> None:
    async with session.begin():
        failures = await repo.recent_failures(session, phone_hash, now, FAILURE_WINDOW)
    if failures >= FAILURES_BEFORE_CHALLENGE:
        await require_challenge(token, ip)


async def issue(
    session: AsyncSession,
    phone: str,
    purpose: OtpPurpose,
    *,
    ip: str | None,
    device_id: str | None,
    now: datetime,
) -> OtpChallenge:
    """Create the challenge and enqueue the SMS in the caller's transaction."""
    code, challenge_id = new_code(phone), uuid7()
    ttl = STEP_UP_TTL if purpose == "step_up" else CODE_TTL
    row = OtpChallenge(
        id=challenge_id,
        phone_hash=keyed_hash(phone, "phone"),
        phone_enc=encrypt_field(phone, PHONE_CONTEXT),
        purpose=purpose,
        code_hash=otp_hash(code, str(challenge_id)),
        attempts=0,
        expires_at=now + ttl,
        ip_hash=keyed_hash(ip, "ip") if ip else None,
        device_id=device_id,
        created_at=now,
    )
    await repo.insert(session, row)
    template, sms_purpose = TEMPLATES[purpose]
    row.sms_message_id = await plan.send_sms(
        session, phone, template, {"code": code}, sms_purpose, now=now
    )
    await session.flush()
    return row


async def send_sign_in(
    session: AsyncSession, body: OtpSendIn, *, ip: str, now: datetime
) -> OtpChallenge:
    phone = parse_phone(body.phone)
    phone_hash = keyed_hash(phone, "phone")
    await enforce_client_limits(ip=ip, device_id=body.device_id)
    await check_challenge(session, phone_hash, body.challenge_token, ip=ip, now=now)
    await enforce_phone_limit(phone_hash)
    async with session.begin():
        user = await users_repo.by_phone_hash(session, phone_hash)
        if user is not None and user.status == "suspended":
            raise ForbiddenError("This number cannot sign in")
        return await issue(session, phone, "sign_in", ip=ip, device_id=body.device_id, now=now)

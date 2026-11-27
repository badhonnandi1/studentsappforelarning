"""Guardian consent by OTP and privacy settings (05 §C.4, NFR-07).

Start binds the challenge to the minor, the relation and the document version in Redis for a
little longer than the code lives (it is left to expire), so the challenge row decides 410
vs 401. Confirm
locks the user row, so two challenges cannot both record a consent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from importlib import resources
from typing import Final

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    UnavailableError,
    ValidationAppError,
)
from app.core.redis import get_json, set_json
from app.core.security.actor import Actor
from app.core.security.crypto import encrypt_field
from app.core.security.hashing import keyed_hash
from app.modules import ops
from app.modules.auth.internal.models import GuardianConsent
from app.modules.auth.internal.repositories import consent as repo
from app.modules.auth.internal.schemas.consent import (
    ConsentDocumentOut,
    ConsentOut,
    GuardianConfirmIn,
    GuardianConfirmOut,
    GuardianStartIn,
    Lang,
    PrivacyIn,
    PrivacyOut,
)
from app.modules.auth.internal.services import otp_send, otp_verify, summary
from app.modules.auth.internal.services.otp_verify import WrongCode

KIND: Final = "guardian_consent"
GUARDIAN_PHONE_CONTEXT = "identity.guardian_consents.guardian_phone"
PENDING_TTL = otp_send.CODE_TTL + timedelta(minutes=10)
DOCS = resources.files("app.modules.auth.internal") / "consent_docs"


def pending_key(challenge_id: uuid.UUID) -> str:
    return f"auth:guardian:{challenge_id}"


async def _checks(
    session: AsyncSession, actor: Actor, phone_hash: bytes, version: str, now: datetime
) -> None:
    user = await summary.signed_in_user(session, actor, lock=True)
    if not summary.is_minor(user, now):
        raise ConflictError("Guardian consent is only needed under 18", code="consent_not_required")
    if user.phone_hash is not None and user.phone_hash == phone_hash:
        raise ValidationAppError(
            "Use your guardian's number, not your own", code="same_phone",
            details={"field": "guardian_phone"},
        )  # fmt: skip
    if await repo.active_consent(session, user.id) is not None:
        raise ConflictError("Guardian consent is already recorded", code="consent_active")
    latest = await repo.latest_version(session, KIND)
    if version != latest:
        raise ValidationAppError(
            "Read and accept the latest consent text", code="consent_version_outdated",
            details={"field": "consent_version", "latest": latest},
        )  # fmt: skip


async def start(
    session: AsyncSession, actor: Actor, body: GuardianStartIn, *, ip: str, now: datetime
) -> tuple[uuid.UUID, datetime]:
    phone = otp_send.parse_phone(body.guardian_phone)
    phone_hash = keyed_hash(phone, "phone")
    await otp_send.enforce_client_limits(ip=ip, device_id=None)
    await otp_send.enforce_phone_limit(phone_hash)
    async with session.begin():
        await _checks(session, actor, phone_hash, body.consent_version, now)
        row = await otp_send.issue(session, phone, KIND, ip=ip, device_id=None, now=now)
        bound = {"user_id": str(actor.user_id), "relation": body.guardian_relation,
                 "version": body.consent_version}  # fmt: skip
        try:
            await set_json(pending_key(row.id), bound, int(PENDING_TTL.total_seconds()))
        except (RedisError, OSError) as exc:
            raise UnavailableError("Try again in a moment") from exc
    return row.id, row.expires_at


async def _bound(challenge_id: uuid.UUID, actor: Actor) -> dict[str, str]:
    try:
        bound = await get_json(pending_key(challenge_id))
    except (RedisError, OSError) as exc:
        raise UnavailableError("Try again in a moment") from exc
    if not isinstance(bound, dict) or bound.get("user_id") != str(actor.user_id):
        raise UnauthorizedError("That code is not right", code="invalid_code")
    return bound


async def confirm(
    session: AsyncSession, actor: Actor, body: GuardianConfirmIn, now: datetime
) -> GuardianConfirmOut:
    bound = await _bound(body.challenge_id, actor)
    result: GuardianConfirmOut | None = None
    async with session.begin():
        user = await summary.signed_in_user(session, actor, lock=True)
        outcome = await otp_verify.consume(session, body.challenge_id, body.code, KIND, now)
        if not isinstance(outcome, WrongCode):
            if await repo.active_consent(session, user.id) is not None:
                raise ConflictError("Guardian consent is already recorded", code="consent_active")
            phone = otp_verify.phone_of(outcome)
            row = GuardianConsent(
                id=uuid.uuid4(), user_id=user.id, consent_version=bound["version"],
                guardian_phone_enc=encrypt_field(phone, GUARDIAN_PHONE_CONTEXT),
                guardian_phone_hash=outcome.phone_hash, scope={"relation": bound["relation"]},
                method="otp", otp_challenge_id=outcome.id, granted_at=now,
            )  # fmt: skip
            await repo.add_consent(session, row)
            target = ops.AuditTarget(type="guardian_consent", id=str(row.id))
            async with ops.audited(
                session, actor, "auth.guardian_consent.record", target, now=now
            ) as audit:
                audit.after = {"version": row.consent_version, "relation": bound["relation"]}
            consent = ConsentOut(status="granted", version=row.consent_version, granted_at=now)
            result = GuardianConfirmOut(consent=consent)
    if isinstance(outcome, WrongCode):
        raise outcome.error()
    if result is None:  # pragma: no cover - every branch above sets it
        raise RuntimeError("guardian confirm produced no result")
    return result


def _privacy_out(row: object) -> PrivacyOut:
    return PrivacyOut.model_validate(row, from_attributes=True)


async def get_privacy(session: AsyncSession, actor: Actor) -> PrivacyOut:
    async with session.begin():
        await summary.signed_in_user(session, actor)
        return _privacy_out(await repo.privacy(session, actor.user_id))


async def put_privacy(session: AsyncSession, actor: Actor, body: PrivacyIn) -> PrivacyOut:
    async with session.begin():
        await summary.signed_in_user(session, actor)
        row = await repo.privacy(session, actor.user_id, lock=True)
        if (
            body.leaderboard_visible is not None
            and body.leaderboard_visible != row.leaderboard_visible
        ):
            if row.opt_out_by == "guardian":
                raise ForbiddenError("Your guardian turned this off")
            row.leaderboard_visible = body.leaderboard_visible
            row.opt_out_by = None if body.leaderboard_visible else "self"
        if body.profile_private is not None:
            row.profile_private = body.profile_private
        await session.flush()
        return _privacy_out(row)


async def get_document(session: AsyncSession, version: str, lang: Lang) -> ConsentDocumentOut:
    row = await repo.document(session, version, lang)
    await session.commit()
    if row is None:
        raise NotFoundError("No such consent document")
    body = (DOCS / f"{row.version}.{row.lang}.md").read_text(encoding="utf-8")
    return ConsentDocumentOut(
        version=row.version, lang=lang, body_markdown=body, published_at=row.published_at
    )

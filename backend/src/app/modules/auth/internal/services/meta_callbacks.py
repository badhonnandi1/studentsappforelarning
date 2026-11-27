"""Meta data-deletion and deauthorise callbacks (05 §C.5).

``signed_request`` is ``base64url(signature).base64url(payload)``; the signature is HMAC-SHA256
of the encoded payload with the app secret, compared in constant time, and the payload must say
``algorithm = HMAC-SHA256``. Any failure is a bare ``400``. A deletion unlinks the identity and
opens an ``identity.data_requests`` row with a confirmation code; support carries it out
until B6. A repeated callback returns the open request's code.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.core.settings import get_settings
from app.modules import ops
from app.modules.auth.internal.models import DataRequest, ExternalIdentity
from app.modules.auth.internal.repositories import identities as identities_repo

PROVIDER = "facebook"
VIA = "facebook_callback"


def _b64url(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def parse_signed_request(signed_request: str, secret: str) -> dict[str, Any]:
    """The signature is checked before the payload is parsed."""
    signature_part, _, payload_part = signed_request.partition(".")
    expected = hmac.new(secret.encode(), payload_part.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(_b64url(signature_part), expected):
            raise ValueError("signature")
        payload = json.loads(_b64url(payload_part))
    except (ValueError, binascii.Error) as exc:
        raise AppError("Bad request") from exc
    if not isinstance(payload, dict) or not payload.get("user_id"):
        raise AppError("Bad request")
    if str(payload.get("algorithm", "")).upper() != "HMAC-SHA256":
        raise AppError("Bad request")
    return payload


def _subject(signed_request: str) -> str:
    secret = get_settings().facebook_app_secret.get_secret_value()
    return str(parse_signed_request(signed_request, secret)["user_id"])


async def _unlink(
    session: AsyncSession, subject: str, reason: str, action: str, now: datetime
) -> ExternalIdentity | None:
    row = await identities_repo.by_subject(session, PROVIDER, subject, lock=True)
    if row is None:
        return None
    if row.unlinked_at is None:
        row.unlinked_at, row.unlink_reason = now, reason
    who = ops.AuditActor(kind="provider")
    target = ops.AuditTarget(type="user", id=str(row.user_id))
    async with ops.audited(session, who, action, target, now=now) as audit:
        audit.after = {"provider": PROVIDER, "unlink_reason": row.unlink_reason}
    return row


async def _open_request(session: AsyncSession, row: ExternalIdentity) -> DataRequest | None:
    stmt = select(DataRequest).where(
        DataRequest.user_id == row.user_id,
        DataRequest.kind == "deletion",
        DataRequest.requested_via == VIA,
        DataRequest.status.in_(("open", "in_progress")),
    )
    return (await session.execute(stmt.limit(1))).scalar_one_or_none()


async def data_deletion(
    session: AsyncSession, signed_request: str, now: datetime
) -> tuple[str, str]:
    """Return ``(status_url, confirmation_code)``. An unknown Facebook user holds no data with
    us; Meta still needs a code, which then has no status page (``404``)."""
    subject = _subject(signed_request)
    async with session.begin():
        row = await _unlink(session, subject, "data_deletion", "auth.identity.data_deletion", now)
        request = await _open_request(session, row) if row is not None else None
        code = request.confirmation_code if request is not None else None
        if code is None:
            code = secrets.token_urlsafe(16)
            if row is not None:
                session.add(DataRequest(
                    user_id=row.user_id, kind="deletion", requested_via=VIA,
                    confirmation_code=code, created_at=now,
                ))  # fmt: skip
    base = get_settings().public_api_url.rstrip("/")
    return f"{base}/v1/auth/social/facebook/deletion-status/{code}", code


async def deauthorize(session: AsyncSession, signed_request: str, now: datetime) -> None:
    subject = _subject(signed_request)
    async with session.begin():
        await _unlink(session, subject, "deauthorized", "auth.identity.deauthorize", now)


async def deletion_status(session: AsyncSession, code: str) -> tuple[str, datetime | None]:
    stmt = select(DataRequest.status, DataRequest.completed_at).where(
        DataRequest.confirmation_code == code
    )
    found = (await session.execute(stmt)).first()
    await session.commit()
    if found is None:
        raise NotFoundError("Unknown confirmation code")
    status, completed_at = found
    return ("completed" if status == "completed" else "received"), completed_at

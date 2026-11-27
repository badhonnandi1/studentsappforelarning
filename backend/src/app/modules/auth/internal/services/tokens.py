"""Access and refresh tokens; rotation with reuse detection; the revocation cache (14 §1.2).

Refresh tokens are 256-bit random strings stored as SHA-256 hashes. Each refresh rotates the
token inside its family; presenting a rotated or revoked token revokes the family and the session
(``auth.refresh.reuse``). API sessions slide to 30 days; staff sessions end 12 h after sign-in.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.core.redis import get_redis
from app.core.security.actor import revoked_key
from app.core.security.hashing import sha256
from app.core.security.jwt import LEEWAY_S, Audience, token_keys
from app.core.settings import get_settings
from app.modules.auth.internal.models import DeviceSession, RefreshToken
from app.modules.auth.internal.repositories import sessions as repo

log = structlog.get_logger(__name__)
REFRESH_BYTES = 32
STAFF_AMR = ("mfa",)  # staff sessions exist only after the SSO MFA check (R-07)


@dataclass(frozen=True)
class Issued:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


def token_hash(raw: str) -> bytes:
    return sha256(raw)


def access_ttl() -> timedelta:
    return timedelta(minutes=get_settings().access_token_minutes)


def refresh_ttl(audience: str) -> timedelta:
    settings = get_settings()
    if audience == "admin":
        return timedelta(hours=settings.staff_refresh_hours)
    return timedelta(days=settings.refresh_token_days)


async def issue(
    session: AsyncSession,
    ds: DeviceSession,
    roles: Iterable[str],
    now: datetime,
    *,
    parent: RefreshToken | None = None,
) -> Issued:
    claims: dict[str, object] = {"sub": str(ds.user_id), "sid": str(ds.id), "roles": list(roles)}
    if ds.sign_in_method == "sso":
        claims.update(sso=True, amr=list(STAFF_AMR))
    audience: Audience = "admin" if ds.audience == "admin" else "api"
    access = token_keys().sign(claims, audience=audience, now=now, ttl=access_ttl())
    raw = secrets.token_urlsafe(REFRESH_BYTES)
    if parent is not None and audience == "admin":
        expires = parent.expires_at  # staff sessions do not slide
    else:
        expires = now + refresh_ttl(audience)
    row = RefreshToken(
        id=uuid7(),
        session_id=ds.id,
        family_id=parent.family_id if parent is not None else uuid7(),
        token_hash=token_hash(raw),
        parent_id=parent.id if parent is not None else None,
        issued_at=now,
        expires_at=expires,
    )
    await repo.add(session, row)
    return Issued(access, now + access_ttl(), raw, expires)


async def mark_revoked(session_ids: Iterable[uuid.UUID]) -> None:
    """After commit: make revoked sessions' access tokens fail on their next request."""
    ttl = int(access_ttl().total_seconds()) + LEEWAY_S + 60
    try:
        redis = get_redis()
        for session_id in session_ids:
            await redis.set(revoked_key(session_id), "1", ex=ttl)
    except (RedisError, OSError):
        log.warning("revocation_cache_write_failed")

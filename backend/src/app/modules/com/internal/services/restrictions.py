"""Mute and ban (05 §D, COM-05). Every write is audited.

``is_restricted(user, scope)`` reads the user's active restrictions through a 60 s Redis cache
(dropped on every write; Redis down falls back to Postgres). A restriction in scope ``global``
(the API's ``all``) covers every scope. A ban of any scope ends all the user's sessions through
the ``SessionRevoker`` AUTH registers; only a global ban also refuses sign-in.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime
from typing import Any

import structlog
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.core.redis import get_json, get_redis, set_json
from app.core.security.actor import Actor
from app.modules import nfr, ops
from app.modules.com.contracts.moderation import Scope, SessionRevoker
from app.modules.com.internal.models import UserRestriction
from app.modules.com.internal.repositories import restrictions as repo
from app.modules.com.internal.schemas.moderation import RestrictionIn

log = structlog.get_logger(__name__)
TTL_S = 60
API_SCOPE = {"all": "global", "community": "community", "profile": "profile"}
_revoker: SessionRevoker | None = None


def set_session_revoker(revoker: SessionRevoker | None) -> None:
    global _revoker
    _revoker = revoker


def revoker() -> SessionRevoker:
    if _revoker is None:
        raise RuntimeError("No SessionRevoker registered (AUTH startup registers it)")
    return _revoker


def _key(user_id: uuid.UUID) -> str:
    return f"com:restrictions:{user_id}"


async def _active(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> list[dict[str, Any]]:
    try:
        cached = await get_json(_key(user_id))
        if isinstance(cached, list):
            return cached
    except (RedisError, OSError):
        log.warning("restriction_cache_unavailable")
    opened = not session.in_transaction()
    rows = await repo.active_for_user(session, user_id, now)
    if opened:
        await session.commit()  # end the read-only transaction so callers can begin() after
    found = [{"kind": r.kind, "scope": r.scope, "starts_at": r.starts_at.isoformat(),
              "ends_at": r.ends_at.isoformat() if r.ends_at else None} for r in rows]  # fmt: skip
    with contextlib.suppress(RedisError, OSError):
        await set_json(_key(user_id), found, TTL_S)
    return found


def _live(row: dict[str, Any], now: datetime) -> bool:
    ends = row["ends_at"]
    return datetime.fromisoformat(row["starts_at"]) <= now and (
        ends is None or datetime.fromisoformat(ends) > now
    )


async def is_restricted(
    session: AsyncSession,
    user_id: uuid.UUID,
    scope: Scope,
    now: datetime,
    *,
    kind: str | None = None,
) -> bool:
    return any(
        _live(r, now) and r["scope"] in ("global", scope) and kind in (None, r["kind"])
        for r in await _active(session, user_id, now)
    )


async def is_banned(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> bool:
    """A live global ban (sign-in refuses these)."""
    rows = await _active(session, user_id, now)
    return any(_live(r, now) and r["kind"] == "ban" and r["scope"] == "global" for r in rows)


def out(row: UserRestriction) -> dict[str, Any]:
    scope = "all" if row.scope == "global" else row.scope
    return {"id": row.id, "user_id": row.user_id, "kind": row.kind, "scope": scope,
            "reason": row.reason, "starts_at": row.starts_at, "ends_at": row.ends_at,
            "lifted_at": row.lifted_at}  # fmt: skip


async def apply(
    session: AsyncSession,
    actor: Actor,
    user_id: uuid.UUID,
    *,
    kind: str,
    scope: str,
    reason: str,
    ends_at: datetime | None,
    now: datetime,
) -> tuple[UserRestriction, list[uuid.UUID]]:
    """Add a restriction in the caller's transaction; return it and the revoked session ids.
    An unknown user surfaces as an ``IntegrityError`` on flush (callers map it to 404)."""
    if ends_at is not None and ends_at <= now:
        raise ValidationAppError("ends_at must be in the future", details={"ends_at": "past"})
    row = UserRestriction(user_id=user_id, kind=kind, scope=API_SCOPE[scope], reason=reason,
                          ends_at=ends_at, created_by=actor.user_id)  # fmt: skip
    row.starts_at = now
    session.add(row)
    await session.flush()
    target = ops.AuditTarget(type="user", id=str(user_id))
    revoked: list[uuid.UUID] = []
    async with ops.audited(
        session, actor, f"com.restriction.{kind}", target, reason=reason, now=now
    ) as audit:
        if kind == "ban":
            revoked = await revoker().revoke_all(session, user_id, now)
        audit.after = {"restriction_id": str(row.id), "scope": row.scope,
                       "ends_at": ends_at.isoformat() if ends_at else None,
                       "sessions_revoked": len(revoked)}  # fmt: skip
    return row, revoked


async def after_commit(user_id: uuid.UUID, revoked: list[uuid.UUID]) -> None:
    if revoked:
        await revoker().after_commit(revoked)
    try:
        await get_redis().delete(_key(user_id))
    except (RedisError, OSError):
        log.warning("restriction_cache_invalidate_failed")


async def lift(
    session: AsyncSession, actor: Actor, restriction_id: uuid.UUID, now: datetime
) -> None:
    async with session.begin():
        row = await repo.get(session, restriction_id)
        if row is None or row.lifted_at is not None:
            raise NotFoundError("Restriction not found")
        target = ops.AuditTarget(type="user", id=str(row.user_id))
        async with ops.audited(session, actor, "com.restriction.lift", target, now=now) as audit:
            audit.before = {"restriction_id": str(row.id), "kind": row.kind, "scope": row.scope}
            row.lifted_at = now
            audit.after = {"lifted_at": now.isoformat()}
    await after_commit(row.user_id, [])


async def create(
    session: AsyncSession, actor: Actor, body: RestrictionIn, now: datetime, idem: nfr.Idem
) -> Any:
    """``POST /v1/admin/moderation/restrictions``; return the JSON body. The idempotency
    record commits with the restriction."""
    try:
        async with session.begin():
            row, revoked = await apply(
                session, actor, body.user_id, kind=body.kind, scope=body.scope,
                reason=body.reason, ends_at=body.ends_at, now=now,
            )  # fmt: skip
            body_out = await idem.record(201, out(row), row.id)
    except IntegrityError as exc:
        raise NotFoundError("User not found") from exc
    await after_commit(body.user_id, revoked)
    return body_out

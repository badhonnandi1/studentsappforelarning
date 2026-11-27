"""``POST /v1/auth/refresh``: rotate a refresh token; detect reuse (05 §C.4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import UnauthorizedError
from app.modules import ops
from app.modules.auth.internal.models import RefreshToken
from app.modules.auth.internal.repositories import sessions as repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import TokenPair
from app.modules.auth.internal.services import summary, tokens
from app.modules.auth.internal.services.sign_in import check_status


@dataclass(frozen=True)
class Reused:
    session_id: uuid.UUID


async def _reuse(session: AsyncSession, row: RefreshToken, now: datetime) -> Reused:
    await repo.revoke_family(session, row.family_id, now)
    ds = await repo.get(session, row.session_id, lock=True)
    if ds is not None and ds.revoked_at is None:
        await repo.revoke(session, ds, "token_reuse", now)
    who = ops.AuditActor(kind="user", user_id=ds.user_id if ds is not None else None)
    target = ops.AuditTarget(type="device_session", id=str(row.session_id))
    async with ops.audited(session, who, "auth.refresh.reuse", target, now=now) as record:
        record.after = {"family_id": str(row.family_id)}
    return Reused(row.session_id)


async def _rotate(session: AsyncSession, raw: str, now: datetime) -> TokenPair | Reused:
    row = await repo.token_by_hash(session, tokens.token_hash(raw))
    if row is None:
        raise UnauthorizedError("Sign in again")
    if row.rotated_at is not None or row.revoked_at is not None:
        return await _reuse(session, row, now)
    if row.expires_at <= now:
        raise UnauthorizedError("Sign in again", code="token_expired")
    ds = await repo.get(session, row.session_id, lock=True)
    if ds is None or ds.revoked_at is not None:
        raise UnauthorizedError("Sign in again")
    user = await users_repo.get(session, ds.user_id, lock=True)
    if user is None:  # pragma: no cover - device_sessions.user_id is a FK
        raise UnauthorizedError("Sign in again")
    check_status(user)
    row.rotated_at = now
    roles = await users_repo.active_roles(session, user.id)
    issued = await tokens.issue(session, ds, roles, now, parent=row)
    ds.last_seen_at = now
    users_repo.touch(user, now)
    return summary.token_pair(issued, ds, await summary.user_summary(session, user, roles, now))


async def refresh(session: AsyncSession, raw: str, now: datetime) -> TokenPair:
    async with session.begin():
        outcome = await _rotate(session, raw, now)
    if isinstance(outcome, Reused):
        await tokens.mark_revoked([outcome.session_id])
        raise UnauthorizedError("Sign in again")
    return outcome

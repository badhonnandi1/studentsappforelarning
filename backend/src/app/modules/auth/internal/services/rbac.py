"""Authorization data owned by AUTH: the grants loader, and audited grant and revoke (05 §C.6).

``can``/``require`` live in ``core.security.actor`` (R-03) and are re-exported here. Granting is
bounded by the granter: a role whose permissions are not all among the granter's own (in that
scope) is refused, so nobody hands out more than they hold. Only ``super_admin`` grants
``super_admin``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

import structlog
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.ids import uuid7
from app.core.security.actor import (
    SUPER_ADMIN,
    Actor,
    Grant,
    GrantsLoader,
    can,
    invalidate_grants,
    require,
)
from app.modules import ops
from app.modules.auth.internal.models import RoleGrant
from app.modules.auth.internal.permissions import ROLE_GRANT, STAFF_ROLES
from app.modules.auth.internal.repositories import rbac as repo
from app.modules.auth.internal.repositories import sessions as sessions_repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.rbac import RoleGrantIn
from app.modules.auth.internal.services.tokens import mark_revoked

__all__ = ["can", "grant", "make_grants_loader", "require", "revoke"]
log = structlog.get_logger(__name__)


def make_grants_loader(sessions: Callable[[], AsyncSession]) -> GrantsLoader:
    async def load(user_id: uuid.UUID) -> list[Grant]:
        async with sessions() as session:
            return await repo.grants_for(session, user_id)

    return load


async def _check_bounded(
    session: AsyncSession, actor: Actor, role_code: str, scope: tuple[str, uuid.UUID | None]
) -> None:
    require(actor, ROLE_GRANT, *scope)
    if actor.is_super_admin:
        return
    held = {g.permission for g in actor.grants if g.covers(*scope)}
    wanted = await repo.role_permissions(session, role_code)
    if role_code == SUPER_ADMIN or not wanted <= held:
        raise ForbiddenError(
            "You cannot grant or revoke a role above your own", code="role_above_own"
        )


async def _after(user_id: uuid.UUID, revoked_sessions: list[uuid.UUID]) -> None:
    try:
        await invalidate_grants(user_id)
    except (RedisError, OSError):
        log.warning("grants_invalidate_failed", user_id=str(user_id))  # 60 s cache bounds it
    await mark_revoked(revoked_sessions)


def _snapshot(row: RoleGrant) -> dict[str, object]:
    scope_id = str(row.scope_id) if row.scope_id else None
    return {
        "user_id": str(row.user_id),
        "role_code": row.role_code,
        "scope_type": row.scope_type,
        "scope_id": scope_id,
    }


async def grant(session: AsyncSession, actor: Actor, body: RoleGrantIn, now: datetime) -> RoleGrant:
    scope = (body.scope_type, body.scope_id)
    async with session.begin():
        if await repo.role(session, body.role_code) is None:
            raise ValidationAppError("Unknown role", code="unknown_role")
        await _check_bounded(session, actor, body.role_code, scope)
        if await users_repo.get(session, body.user_id, lock=True) is None:  # serialises grants
            raise NotFoundError("User not found")
        if await repo.active_duplicate(session, body.user_id, body.role_code, *scope):
            raise ConflictError("The user already holds this role in this scope")
        row = RoleGrant(
            id=uuid7(),
            user_id=body.user_id,
            role_code=body.role_code,
            scope_type=body.scope_type,
            scope_id=body.scope_id,
            granted_by=actor.user_id,
            granted_at=now,
        )
        target = ops.AuditTarget(type="role_grant", id=str(row.id))
        async with ops.audited(
            session, actor, "auth.role.grant", target, reason=body.reason, now=now
        ) as audit:
            await repo.add(session, row)
            audit.after = _snapshot(row)
    await _after(body.user_id, [])
    return row


async def revoke(session: AsyncSession, actor: Actor, grant_id: uuid.UUID, now: datetime) -> None:
    """Revoking a staff role also ends the user's admin sessions, so a stale ``roles`` claim
    (super admin bypass included) does not outlive the grant."""
    ended: list[uuid.UUID] = []
    async with session.begin():
        row = await repo.get_grant(session, grant_id)
        if row is None or row.revoked_at is not None:
            raise NotFoundError("Role grant not found")
        await _check_bounded(session, actor, row.role_code, (row.scope_type, row.scope_id))
        target = ops.AuditTarget(type="role_grant", id=str(row.id))
        async with ops.audited(session, actor, "auth.role.revoke", target, now=now) as audit:
            audit.before = _snapshot(row)
            row.revoked_at = now
            if row.role_code in STAFF_ROLES:
                for ds in await sessions_repo.live_for_user(session, row.user_id):
                    if ds.audience == "admin":
                        await sessions_repo.revoke(session, ds, "admin", now)
                        ended.append(ds.id)
            audit.after = {"revoked_at": now.isoformat(), "ended_sessions": len(ended)}
    await _after(row.user_id, ended)

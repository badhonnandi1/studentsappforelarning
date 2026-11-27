"""Who is calling, and may they do this? (04 §4 R-03: authorization never imports AUTH.)

Access tokens carry ``sub``, ``sid`` and ``roles``. Grants (permission plus scope) are read from
the ``auth:grants:{user_id}`` cache that AUTH owns; on a miss the loader AUTH registers at start
up fills it. Without a loader the actor has no grants, so every permission check fails closed.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field

import structlog
from redis.exceptions import RedisError

from app.core.errors import ForbiddenError
from app.core.redis import get_json, get_redis, set_json

log = structlog.get_logger(__name__)
GRANTS_TTL_S = 60
SUPER_ADMIN = "super_admin"


@dataclass(frozen=True)
class Grant:
    permission: str
    scope_type: str = "global"  # global | subject | tenant
    scope_id: uuid.UUID | None = None

    def covers(self, scope_type: str, scope_id: uuid.UUID | None) -> bool:
        if self.scope_type == "global":
            return True
        return self.scope_type == scope_type and self.scope_id == scope_id


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    session_id: uuid.UUID
    roles: frozenset[str]
    audience: str = "api"
    sso: bool = False
    amr: tuple[str, ...] = ()
    grants: tuple[Grant, ...] = field(default=())

    @property
    def is_super_admin(self) -> bool:
        return SUPER_ADMIN in self.roles


GrantsLoader = Callable[[uuid.UUID], Awaitable[Iterable[Grant]]]
_loader: GrantsLoader | None = None


def set_grants_loader(loader: GrantsLoader | None) -> None:
    """AUTH registers its DB-backed loader at start up (and tests install fakes)."""
    global _loader
    _loader = loader


def grants_key(user_id: uuid.UUID) -> str:
    return f"auth:grants:{user_id}"


def revoked_key(session_id: uuid.UUID) -> str:
    return f"revoked_sess:{session_id}"


def _decode(raw: object) -> tuple[Grant, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        Grant(g["permission"], g["scope_type"], uuid.UUID(g["scope_id"]) if g["scope_id"] else None)
        for g in raw
    )


def _encode(grants: Iterable[Grant]) -> list[dict[str, str | None]]:
    return [
        {
            "permission": g.permission,
            "scope_type": g.scope_type,
            "scope_id": str(g.scope_id) if g.scope_id else None,
        }
        for g in grants
    ]


async def load_grants(user_id: uuid.UUID) -> tuple[Grant, ...]:
    try:
        cached = await get_json(grants_key(user_id))
        if cached is not None:
            return _decode(cached)
    except (RedisError, OSError):
        log.warning("grants_cache_unavailable")
    if _loader is None:
        return ()
    grants = tuple(await _loader(user_id))
    with contextlib.suppress(RedisError, OSError):
        await set_json(grants_key(user_id), _encode(grants), GRANTS_TTL_S)
    return grants


async def invalidate_grants(user_id: uuid.UUID) -> None:
    await get_redis().delete(grants_key(user_id))


async def is_session_revoked(session_id: uuid.UUID, *, fail_closed: bool) -> bool:
    """One Redis ``EXISTS`` per request (18 §2). Admin requests fail closed when Redis is down;
    user requests fail open, bounded by the 15-minute access token lifetime."""
    try:
        return bool(await get_redis().exists(revoked_key(session_id)))
    except (RedisError, OSError):
        log.warning("revocation_check_unavailable", fail_closed=fail_closed)
        return fail_closed


def can(
    actor: Actor, permission: str, scope_type: str = "global", scope_id: uuid.UUID | None = None
) -> bool:
    if actor.is_super_admin:
        log.info("rbac_super_admin_bypass", user_id=str(actor.user_id), permission=permission)
        return True
    return any(g.permission == permission and g.covers(scope_type, scope_id) for g in actor.grants)


def require(
    actor: Actor, permission: str, scope_type: str = "global", scope_id: uuid.UUID | None = None
) -> None:
    if not can(actor, permission, scope_type, scope_id):
        raise ForbiddenError("You do not have permission for this action")

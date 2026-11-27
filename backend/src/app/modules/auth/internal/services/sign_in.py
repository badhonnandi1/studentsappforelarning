"""Shared sign-in: status check, device session (reused per device), tokens, audit, outbox.

Every sign-in method ends here, inside the caller's transaction (05 §C.2). Revocations of
sessions evicted by the per-user cap reach Redis after commit (``after_commit``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.core.ids import uuid7
from app.core.security.hashing import keyed_hash
from app.core.settings import get_settings
from app.modules import ops
from app.modules.auth.contracts.events import USER_SIGNED_IN, SignInMethod, UserSignedIn
from app.modules.auth.internal.models import DeviceSession, User
from app.modules.auth.internal.repositories import sessions as sessions_repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import DeviceInfo, TokenPair
from app.modules.auth.internal.services import summary, tokens
from app.modules.nfr import make_event, publish

BLOCKED_STATUSES = frozenset({"suspended", "deleted"})


@dataclass
class Started:
    pair: TokenPair
    session: DeviceSession
    evicted: list[uuid.UUID] = field(default_factory=list)


def check_status(user: User) -> None:
    if user.status in BLOCKED_STATUSES:
        raise ForbiddenError("This account cannot sign in")


async def _device_session(
    session: AsyncSession,
    user: User,
    method: str,
    device: DeviceInfo,
    *,
    audience: str,
    ip: str | None,
    now: datetime,
) -> tuple[DeviceSession, list[uuid.UUID]]:
    ds = await sessions_repo.live_for_device(session, user.id, device.device_id, audience)
    if ds is not None:  # one session per device: re-sign-in starts a new token family
        await sessions_repo.revoke_tokens(session, ds.id, now)
    else:
        ds = DeviceSession(id=uuid7(), user_id=user.id, device_id=device.device_id, created_at=now)
        session.add(ds)
    ds.platform, ds.app_version, ds.model = device.platform, device.app_version, device.model
    ds.audience, ds.sign_in_method, ds.last_seen_at = audience, method, now
    ds.ip_hash = keyed_hash(ip, "ip") if ip else None
    await session.flush()
    return ds, await _evict_over_cap(session, user.id, keep=ds.id, now=now)


async def _evict_over_cap(
    session: AsyncSession, user_id: uuid.UUID, *, keep: uuid.UUID, now: datetime
) -> list[uuid.UUID]:
    cap = get_settings().max_sessions_per_user
    live = [s for s in await sessions_repo.live_for_user(session, user_id) if s.id != keep]
    evicted = live[max(cap - 1, 0) :]  # newest first, so the oldest go
    for old in evicted:
        await sessions_repo.revoke(session, old, "session_limit", now)
    return [old.id for old in evicted]


async def start_session(
    session: AsyncSession,
    user: User,
    method: SignInMethod,
    device: DeviceInfo,
    *,
    ip: str | None,
    now: datetime,
    audience: str = "api",
    created: bool = False,
) -> Started:
    check_status(user)
    ds, evicted = await _device_session(
        session, user, method, device, audience=audience, ip=ip, now=now
    )
    roles = await users_repo.active_roles(session, user.id)
    issued = await tokens.issue(session, ds, roles, now)
    users_repo.touch(user, now)
    who = ops.AuditActor(kind="user", user_id=user.id, roles=tuple(roles))
    target = ops.AuditTarget(type="device_session", id=str(ds.id))
    async with ops.audited(session, who, "auth.session.sign_in", target, now=now) as record:
        record.after = {"method": method, "platform": device.platform, "created": created}
    payload = UserSignedIn(
        session_id=ds.id, method=method, platform=device.platform, created=created
    )
    event = make_event(
        USER_SIGNED_IN,
        aggregate_type="user",
        aggregate_id=user.id,
        payload=payload.model_dump(mode="json"),
        now=now,
        user_id=user.id,
    )
    await publish(session, event)
    user_summary = await summary.user_summary(session, user, roles, now)
    return Started(summary.token_pair(issued, ds, user_summary), ds, evicted)


async def after_commit(started: Started) -> None:
    await tokens.mark_revoked(started.evicted)

"""``auth.sessions.purge_stale`` (daily, ``maintenance``): sessions idle for 90 days end.

A pure update: the session and its refresh tokens are marked revoked (reason ``inactive``);
nothing is deleted. Access tokens live 15 minutes, so no Redis revocation is needed. OAuth
nonces and state expire by Redis TTL, so there is nothing to clean for them.
"""

from __future__ import annotations

from datetime import time, timedelta
from typing import Any

import structlog
from sqlalchemy import select, update

from app.modules import nfr
from app.modules.auth.internal.models import DeviceSession, RefreshToken
from app.modules.nfr.contracts.jobs import JobContext

log = structlog.get_logger(__name__)
KIND = "auth.sessions.purge_stale"
IDLE = timedelta(days=90)
BATCH = 5000
MAX_BATCHES = 20
PERIODIC = nfr.Periodic(KIND, "maintenance", nfr.daily_dhaka(time(3), "auth-purge-stale"))


async def handle(ctx: JobContext, payload: dict[str, Any]) -> None:
    del payload
    session, cutoff, total = ctx.session, ctx.now - IDLE, 0
    for _ in range(MAX_BATCHES):
        ids = (
            select(DeviceSession.id)
            .where(DeviceSession.revoked_at.is_(None), DeviceSession.last_seen_at < cutoff)
            .limit(BATCH)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        ended = (
            (
                await session.execute(
                    update(DeviceSession)
                    .where(DeviceSession.id.in_(ids))
                    .values(revoked_at=ctx.now, revoke_reason="inactive")
                    .returning(DeviceSession.id)
                )
            )
            .scalars()
            .all()
        )
        if ended:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.session_id.in_(ended), RefreshToken.revoked_at.is_(None))
                .values(revoked_at=ctx.now)
            )
        total += len(ended)
        if len(ended) < BATCH:
            break
    log.info("auth_sessions_purged", count=total)

"""List and revoke device sessions; logout (05 §D ``/v1/me/sessions``, ``/v1/auth/logout``)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.security.actor import Actor
from app.modules import ops
from app.modules.auth.internal.models import DeviceSession
from app.modules.auth.internal.repositories import sessions as repo
from app.modules.auth.internal.services.tokens import mark_revoked


async def list_live(session: AsyncSession, actor: Actor) -> list[DeviceSession]:
    rows = await repo.live_for_user(session, actor.user_id)
    await session.commit()  # end the read-only transaction the query opened
    return [row for row in rows if row.audience == "api"]


async def logout(session: AsyncSession, actor: Actor, now: datetime) -> None:
    async with session.begin():
        ds = await repo.get(session, actor.session_id, lock=True)
        if ds is not None and ds.user_id == actor.user_id and ds.revoked_at is None:
            await repo.revoke(session, ds, "logout", now)
    await mark_revoked([actor.session_id])


async def revoke_own(
    session: AsyncSession, actor: Actor, session_id: uuid.UUID, now: datetime
) -> None:
    async with session.begin():
        ds = await repo.get(session, session_id, lock=True)
        if ds is None or ds.user_id != actor.user_id or ds.revoked_at is not None:
            raise NotFoundError("Session not found")
        target = ops.AuditTarget(type="device_session", id=str(ds.id))
        async with ops.audited(session, actor, "auth.session.revoke", target, now=now) as rec:
            rec.after = {"reason": "user"}
            await repo.revoke(session, ds, "user", now)
    await mark_revoked([session_id])

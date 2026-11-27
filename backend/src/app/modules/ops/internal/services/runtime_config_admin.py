"""``PUT /v1/admin/runtime-config/{key}``: the change and its audit row in one transaction."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.actor import Actor
from app.modules import nfr
from app.modules.ops.contracts.audit import AuditTarget
from app.modules.ops.internal.services.audited import audited

ACTION = "ops.runtime_config.update"


async def update(
    session: AsyncSession, actor: Actor, key: str, value: Any, reason: str, now: datetime
) -> Any:
    async with session.begin():
        target = AuditTarget(type="runtime_config", id=key)
        async with audited(session, actor, ACTION, target, reason=reason, now=now) as audit:
            before, after = await nfr.set_runtime_value(
                session, key, value, actor_id=actor.user_id, now=now
            )
            audit.before, audit.after = {"value": before}, {"value": after}
    await nfr.invalidate_runtime_config()
    return after

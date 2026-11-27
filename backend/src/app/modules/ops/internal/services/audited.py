"""``audited()``: an admin or security change and its audit row commit together (01 §6).

    async with session.begin():
        async with ops.audited(session, actor, "ops.runtime_config.update", target,
                               reason=reason) as audit:
            audit.before = {"value": old}
            ...change...
            audit.after = {"value": new}

The row is written only when the block succeeds, inside the caller's transaction, so a rolled
back change leaves no audit row and a committed change always has one. ``before`` and ``after``
keep only the changed fields; PII becomes a keyed hash and other secrets are dropped.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import get_clock
from app.core.errors import ValidationAppError
from app.core.ids import uuid7
from app.core.logging import is_sensitive
from app.core.request_context import current_client_ip, current_request_id
from app.core.security.actor import Actor
from app.core.security.hashing import keyed_hash
from app.modules.ops.contracts.audit import AuditActor, AuditTarget
from app.modules.ops.internal.models import AuditLog
from app.modules.ops.internal.models.audit import ACTION_PATTERN
from app.modules.ops.internal.repositories import audit as repo

REASON_VERBS = frozenset({"grant", "refund", "extend", "invalidate"})  # 01 §3.5 reason rule
_ACTION = re.compile(ACTION_PATTERN)
_MISSING = object()


@dataclass
class AuditRecord:
    target: AuditTarget
    before: Mapping[str, Any] | None = None
    after: Mapping[str, Any] | None = None


def _hashed(key: str, value: Any) -> Any:
    if value is None:
        return None
    lowered = key.lower()
    if "phone" in lowered:
        return {"hash": keyed_hash(str(value), "phone").hex()}
    if "email" in lowered:
        return {"hash": keyed_hash(str(value), "email").hex()}
    return "[redacted]"


def redact(values: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if values is None:
        return None
    out: dict[str, Any] = {}
    for key, value in values.items():
        if is_sensitive(str(key)):
            out[key] = _hashed(str(key), value)
        elif isinstance(value, Mapping):
            out[key] = redact(value)
        else:
            out[key] = to_jsonable_python(value)
    return out


def changed(
    before: Mapping[str, Any] | None, after: Mapping[str, Any] | None
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if before is None or after is None:
        return redact(before), redact(after)
    keys = [k for k in {**before, **after} if before.get(k, _MISSING) != after.get(k, _MISSING)]
    return (
        redact({k: before[k] for k in keys if k in before}),
        redact({k: after[k] for k in keys if k in after}),
    )


def needs_reason(action: str) -> bool:
    return action.rsplit(".", 1)[-1] in REASON_VERBS


@asynccontextmanager
async def audited(
    session: AsyncSession,
    actor: Actor | AuditActor,
    action: str,
    target: AuditTarget,
    *,
    reason: str | None = None,
    before: Mapping[str, Any] | None = None,
    module: str | None = None,
    now: datetime | None = None,
) -> AsyncIterator[AuditRecord]:
    if not session.in_transaction():
        raise RuntimeError("audited() needs the caller's transaction")
    if not _ACTION.match(action):
        raise ValueError(f"audit action {action!r} must look like 'module.thing.verb'")
    if needs_reason(action) and not (reason and reason.strip()):
        raise ValidationAppError(
            "A reason is required for this action", details={"reason": "required"}
        )
    who = actor if isinstance(actor, AuditActor) else AuditActor.of(actor)
    record = AuditRecord(target=target, before=before)
    yield record
    at = (now or get_clock().now()).astimezone(UTC)
    ip = current_client_ip()
    old, new = changed(record.before, record.after)
    await repo.insert(
        session,
        AuditLog(
            id=uuid7(),
            occurred_on=at.date(),
            occurred_at=at,
            actor_user_id=who.user_id,
            actor_kind=who.kind,
            actor_roles=list(who.roles),
            action=action,
            module=module or action.split(".", 1)[0],
            target_type=record.target.type,
            target_id=record.target.id,
            before=old,
            after=new,
            reason=reason,
            ip_hash=keyed_hash(ip, "ip") if ip else None,
            request_id=current_request_id(),
            tenant_id=who.tenant_id,
        ),
    )

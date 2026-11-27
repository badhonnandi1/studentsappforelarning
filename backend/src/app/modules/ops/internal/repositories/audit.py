"""``ops.audit_log`` SQL: insert and keyset search (newest first)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.ops.internal.models import AuditLog


@dataclass(frozen=True)
class AuditFilters:
    start: datetime
    end: datetime
    actor_user_id: uuid.UUID | None = None
    target_type: str | None = None
    target_id: str | None = None
    action: str | None = None


async def insert(session: AsyncSession, row: AuditLog) -> None:
    session.add(row)
    await session.flush()


async def search(
    session: AsyncSession,
    filters: AuditFilters,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[AuditLog]:
    stmt = select(AuditLog).where(
        AuditLog.occurred_on >= filters.start.date(),  # partition pruning
        AuditLog.occurred_on <= filters.end.date(),
        AuditLog.occurred_at >= filters.start,
        AuditLog.occurred_at < filters.end,
    )
    if filters.actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == filters.actor_user_id)
    if filters.target_type is not None:
        stmt = stmt.where(AuditLog.target_type == filters.target_type)
    if filters.target_id is not None:
        stmt = stmt.where(AuditLog.target_id == filters.target_id)
    if filters.action is not None:
        stmt = stmt.where(AuditLog.action == filters.action)
    if after is not None:
        stmt = stmt.where(tuple_(AuditLog.occurred_at, AuditLog.id) < tuple_(*after))
    stmt = stmt.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())

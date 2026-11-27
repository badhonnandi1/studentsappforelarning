"""Audit search for staff (``audit.read``): newest first, at most 93 days per query."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.core.pagination import decode_cursor, encode_cursor
from app.modules.ops.internal.models import AuditLog
from app.modules.ops.internal.repositories import audit as repo
from app.modules.ops.internal.repositories.audit import AuditFilters

MAX_RANGE = timedelta(days=93)
DEFAULT_RANGE = timedelta(days=30)


def time_range(
    start: datetime | None, end: datetime | None, now: datetime
) -> tuple[datetime, datetime]:
    end = end or now
    start = start or end - DEFAULT_RANGE
    if start >= end:
        raise ValidationAppError("'from' must be before 'to'", details={"from": "after_to"})
    if end - start > MAX_RANGE:
        raise ValidationAppError("At most 93 days per query", details={"range": "too_long"})
    return start, end


async def search(
    session: AsyncSession, filters: AuditFilters, cursor: str | None, limit: int
) -> tuple[list[AuditLog], str | None]:
    raw = decode_cursor(cursor, 2)
    after = None
    if raw is not None:
        try:
            after = (datetime.fromisoformat(raw[0]), uuid.UUID(raw[1]))
        except (TypeError, ValueError) as exc:
            raise ValidationAppError("Invalid cursor", details={"cursor": "malformed"}) from exc
    rows = await repo.search(session, filters, after, limit + 1)
    if len(rows) <= limit:
        return rows, None
    last = rows[limit - 1]
    return rows[:limit], encode_cursor([last.occurred_at.isoformat(), str(last.id)])

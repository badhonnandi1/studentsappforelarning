"""``community.content_reports`` queries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.com.internal.models import ContentReport


async def get(session: AsyncSession, report_id: uuid.UUID) -> ContentReport | None:
    return await session.get(ContentReport, report_id, with_for_update=True)


async def page(
    session: AsyncSession,
    status: str | None,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[ContentReport]:
    """Oldest first (a work queue), after the previous page's last ``(created_at, id)``."""
    stmt = select(ContentReport)
    if status is not None:
        stmt = stmt.where(ContentReport.status == status)
    if after is not None:
        key = tuple_(ContentReport.created_at, ContentReport.id)
        stmt = stmt.where(key > tuple_(literal(after[0]), literal(after[1])))
    stmt = stmt.order_by(ContentReport.created_at, ContentReport.id)
    return list((await session.execute(stmt.limit(limit + 1))).scalars())

"""Moderation terms: an in-process index of active terms (refreshed every 5 min) and admin queries.

The index maps each fold family (``en`` for English terms, ``bn`` for Bangla and Banglish) to
``{folded token tuple: highest severity}``, so matching is a dict lookup per n-gram. A write in this process drops the index; other processes pick it up within
5 minutes.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

from sqlalchemy import literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.com.internal.models import ModerationTerm

REFRESH_S = 300
TermIndex = dict[str, dict[tuple[str, ...], int]]
_index: tuple[float, TermIndex] | None = None


def family_of(lang: str) -> str:
    return "en" if lang == "en" else "bn"


def invalidate() -> None:
    global _index
    _index = None


async def active_index(session: AsyncSession) -> TermIndex:
    global _index
    if _index is not None and _index[0] > time.monotonic():
        return _index[1]
    cols = (ModerationTerm.lang, ModerationTerm.term_folded, ModerationTerm.severity)
    stmt = select(*cols).where(ModerationTerm.is_active.is_(True))
    index: TermIndex = {}
    for lang, folded, severity in (await session.execute(stmt)).all():
        family = index.setdefault(family_of(lang), {})
        key = tuple(folded.split())
        family[key] = max(severity, family.get(key, 0))
    _index = (time.monotonic() + REFRESH_S, index)
    return index


async def by_key(session: AsyncSession, lang: str, folded: str) -> ModerationTerm | None:
    stmt = select(ModerationTerm).where(
        ModerationTerm.lang == lang, ModerationTerm.term_folded == folded
    )
    return (await session.execute(stmt.with_for_update())).scalar_one_or_none()


async def get(session: AsyncSession, term_id: uuid.UUID) -> ModerationTerm | None:
    return await session.get(ModerationTerm, term_id, with_for_update=True)


async def page(
    session: AsyncSession, lang: str | None, after: tuple[datetime, uuid.UUID] | None, limit: int
) -> list[ModerationTerm]:
    """Newest first, after the ``(created_at, id)`` of the previous page's last row."""
    stmt = select(ModerationTerm)
    if lang is not None:
        stmt = stmt.where(ModerationTerm.lang == lang)
    if after is not None:
        key = tuple_(ModerationTerm.created_at, ModerationTerm.id)
        stmt = stmt.where(key < tuple_(literal(after[0]), literal(after[1])))
    stmt = stmt.order_by(ModerationTerm.created_at.desc(), ModerationTerm.id.desc())
    return list((await session.execute(stmt.limit(limit + 1))).scalars())

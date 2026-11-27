"""Admin term list: add (stored folded), deactivate, page. Audited (05 §D)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationAppError
from app.core.pagination import time_id_after, time_id_cursor
from app.core.security.actor import Actor
from app.modules import ops
from app.modules.com.internal.models import ModerationTerm
from app.modules.com.internal.repositories import terms as repo
from app.modules.com.internal.schemas.moderation import SEVERITY, SEVERITY_NAME, TermIn, TermOut
from app.modules.com.internal.services.moderate import fold_term


def term_out(row: ModerationTerm) -> TermOut:
    return TermOut(
        id=row.id, lang=row.lang, term_folded=row.term_folded,
        severity=SEVERITY_NAME[row.severity], category=row.category,
        is_active=row.is_active, created_at=row.created_at,
    )  # fmt: skip


async def add(session: AsyncSession, actor: Actor, body: TermIn, now: datetime) -> TermOut:
    folded = fold_term(body.lang, body.term)
    if not folded:
        raise ValidationAppError("The term is empty after folding", details={"term": "empty"})
    async with session.begin():
        row = await repo.by_key(session, body.lang, folded)
        if row is not None and row.is_active:
            raise ConflictError("This term is already on the list")
        target_id = str(row.id) if row is not None else None
        if row is None:
            row = ModerationTerm(lang=body.lang, term_folded=folded, created_by=actor.user_id)
            row.created_at = now
            session.add(row)
        row.severity, row.category, row.is_active = SEVERITY[body.severity], body.category, True
        await session.flush()
        target = ops.AuditTarget(type="moderation_term", id=target_id or str(row.id))
        async with ops.audited(session, actor, "com.term.create", target, now=now) as audit:
            audit.after = {"lang": row.lang, "term_folded": folded, "severity": row.severity,
                           "category": row.category}  # fmt: skip
        out = term_out(row)
    repo.invalidate()
    return out


async def deactivate(
    session: AsyncSession, actor: Actor, term_id: uuid.UUID, now: datetime
) -> None:
    async with session.begin():
        row = await repo.get(session, term_id)
        if row is None or not row.is_active:
            raise NotFoundError("Term not found")
        target = ops.AuditTarget(type="moderation_term", id=str(row.id))
        async with ops.audited(session, actor, "com.term.delete", target, now=now) as audit:
            audit.before = {"term_folded": row.term_folded, "is_active": True}
            row.is_active = False
            audit.after = {"is_active": False}
    repo.invalidate()


async def page(
    session: AsyncSession, lang: str | None, cursor: str | None, limit: int
) -> tuple[list[TermOut], str | None]:
    rows = await repo.page(session, lang, time_id_after(cursor), limit)
    await session.commit()
    more = len(rows) > limit
    rows = rows[:limit]
    last = rows[-1] if more else None
    next_cursor = time_id_cursor(last.created_at, last.id) if last else None
    return [term_out(r) for r in rows], next_cursor

"""User reports and their resolution (05 §D). Resolving is audited and idempotent; it may
apply a restriction to the reported user.

``target_id`` names the user for ``user``, ``display_name`` and ``profile_photo`` reports, so
only those can carry a restriction. Post reports arrive with B2 content; until then a post or
``other`` report can only be dismissed or actioned without one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.pagination import time_id_after, time_id_cursor
from app.core.security.actor import Actor
from app.modules import nfr, ops
from app.modules.com.internal.models import ContentReport
from app.modules.com.internal.repositories import reports as repo
from app.modules.com.internal.schemas.moderation import ReportIn, ReportOut, ResolveIn
from app.modules.com.internal.services import restrictions
from app.modules.com.internal.services.moderate import ensure_allowed

USER_TARGETS = frozenset({"user", "display_name", "profile_photo"})


async def create(session: AsyncSession, actor: Actor, body: ReportIn, now: datetime) -> uuid.UUID:
    if await restrictions.is_restricted(session, actor.user_id, "community", now):
        raise ForbiddenError("Your account is restricted from reporting", code="restricted")
    if body.text:
        await ensure_allowed(session, body.text, "content_report", user_id=actor.user_id)
    async with session.begin():
        row = ContentReport(reporter_user_id=actor.user_id, target_type=body.target_type,
                            target_id=str(body.target_id), reason=body.reason, text=body.text)  # fmt: skip
        row.created_at = now
        session.add(row)
        await session.flush()
        target = ops.AuditTarget(type="content_report", id=str(row.id))
        async with ops.audited(session, actor, "com.report.create", target, now=now) as audit:
            audit.after = {"target_type": row.target_type, "target_id": row.target_id,
                           "reason": row.reason}  # fmt: skip
    return row.id


async def page(
    session: AsyncSession, status: str | None, cursor: str | None, limit: int
) -> tuple[list[ReportOut], str | None]:
    rows = await repo.page(session, status, time_id_after(cursor), limit)
    await session.commit()
    last = rows[limit - 1] if len(rows) > limit else None
    next_cursor = time_id_cursor(last.created_at, last.id) if last else None
    return [ReportOut.model_validate(r) for r in rows[:limit]], next_cursor


def _restriction_user(report: ContentReport) -> uuid.UUID:
    if report.target_type not in USER_TARGETS:
        raise ValidationAppError(
            "Only reports about a user can carry a restriction",
            details={"restriction": "target_not_a_user"},
        )
    return uuid.UUID(report.target_id)


async def resolve(
    session: AsyncSession,
    actor: Actor,
    report_id: uuid.UUID,
    body: ResolveIn,
    now: datetime,
    idem: nfr.Idem,
) -> Any:
    """Return the JSON body; the idempotency record commits with the resolution."""
    if body.restriction is not None and body.decision != "action_taken":
        raise ValidationAppError(
            "A restriction needs decision action_taken", details={"restriction": "needs_action"}
        )
    user_id: uuid.UUID | None = None
    revoked: list[uuid.UUID] = []
    try:
        async with session.begin():
            report = await repo.get(session, report_id)
            if report is None:
                raise NotFoundError("Report not found")
            if report.status != "open":
                raise ConflictError("This report is already resolved")
            restriction_id = None
            if (spec := body.restriction) is not None:
                user_id = _restriction_user(report)
                row, revoked = await restrictions.apply(
                    session, actor, user_id, kind=spec.kind, scope=spec.scope,
                    reason=body.note, ends_at=spec.ends_at, now=now,
                )  # fmt: skip
                restriction_id = str(row.id)
            target = ops.AuditTarget(type="content_report", id=str(report.id))
            async with ops.audited(
                session, actor, "com.report.resolve", target, reason=body.note, now=now
            ) as audit:
                audit.before = {"status": report.status}
                report.status = "dismissed" if body.decision == "dismiss" else "actioned"
                report.resolved_by, report.resolved_at = actor.user_id, now
                audit.after = {"status": report.status, "restriction_id": restriction_id}
            body_out = await idem.record(200, ReportOut.model_validate(report), report.id)
    except IntegrityError as exc:
        raise NotFoundError("The reported user does not exist") from exc
    if user_id is not None:
        await restrictions.after_commit(user_id, revoked)
    return body_out

"""Report queue, resolution and restrictions under ``/v1/admin/moderation`` (05 §D).
Staff permission ``moderation``; the POSTs need an ``Idempotency-Key``."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.pagination import DEFAULT_LIMIT, Limit, Page
from app.core.security.actor import Actor
from app.core.security.deps import staff_permission
from app.modules import nfr
from app.modules.com.internal.schemas.moderation import (
    ReportOut,
    ResolveIn,
    RestrictionIn,
    RestrictionOut,
)
from app.modules.com.internal.services import reports, restrictions

router = APIRouter(prefix="/v1/admin/moderation", tags=["admin"])
moderator = staff_permission("moderation")  # one callable, so FastAPI resolves it once
Moderator = Annotated[Actor, Depends(moderator)]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]


async def moderator_id(actor: Moderator) -> uuid.UUID:
    return actor.user_id


ResolveIdem = Annotated[nfr.Idem, Depends(nfr.idempotent("com.report.resolve", user=moderator_id))]
RestrictIdem = Annotated[
    nfr.Idem, Depends(nfr.idempotent("com.restriction.create", user=moderator_id))
]


@router.get("/reports", response_model=Page[ReportOut])
async def list_reports(
    _actor: Moderator,
    session: Session,
    status: Literal["open", "actioned", "dismissed"] | None = None,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Page[ReportOut]:
    items, next_cursor = await reports.page(session, status, cursor, limit)
    return Page[ReportOut](items=items, next_cursor=next_cursor)


@router.post("/reports/{report_id}:resolve", response_model=ReportOut)
async def resolve_report(
    report_id: uuid.UUID,
    body: ResolveIn,
    actor: Moderator,
    session: Session,
    clock: Now,
    idem: ResolveIdem,
) -> Response:
    if idem.replay is not None:
        return idem.replay
    out = await reports.resolve(session, actor, report_id, body, clock.now(), idem)
    return JSONResponse(out, status_code=200)


@router.post("/restrictions", status_code=201, response_model=RestrictionOut)
async def create_restriction(
    body: RestrictionIn, actor: Moderator, session: Session, clock: Now, idem: RestrictIdem
) -> Response:
    if idem.replay is not None:
        return idem.replay
    out = await restrictions.create(session, actor, body, clock.now(), idem)
    return JSONResponse(out, status_code=201)


@router.delete("/restrictions/{restriction_id}", status_code=204)
async def lift_restriction(
    restriction_id: uuid.UUID, actor: Moderator, session: Session, clock: Now
) -> Response:
    await restrictions.lift(session, actor, restriction_id, clock.now())
    return Response(status_code=204)

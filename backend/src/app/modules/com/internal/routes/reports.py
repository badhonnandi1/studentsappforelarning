"""``POST /v1/reports`` (05 §D): 20 per user per day; the text is moderated."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.security.actor import Actor
from app.core.security.deps import user_tier
from app.modules.com.internal.schemas.moderation import ReportCreated, ReportIn
from app.modules.com.internal.services import reports

router = APIRouter(prefix="/v1/reports", tags=["community"])


@router.post("", status_code=201, response_model=ReportCreated)
async def create_report(
    body: ReportIn,
    actor: Annotated[Actor, Depends(user_tier("report"))],
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ReportCreated:
    return ReportCreated(report_id=await reports.create(session, actor, body, clock.now()))

"""``GET/POST/DELETE /v1/admin/moderation/terms[/{id}]`` (05 §D). Staff: ``moderation``."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.pagination import DEFAULT_LIMIT, Limit, Page
from app.core.security.actor import Actor
from app.core.security.deps import staff_permission
from app.modules.com.internal.schemas.moderation import TermIn, TermOut
from app.modules.com.internal.services import terms

router = APIRouter(prefix="/v1/admin/moderation/terms", tags=["admin"])
Moderator = Annotated[Actor, Depends(staff_permission("moderation"))]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("", response_model=Page[TermOut])
async def list_terms(
    _actor: Moderator,
    session: Session,
    lang: Literal["bn", "en", "banglish"] | None = None,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Page[TermOut]:
    items, next_cursor = await terms.page(session, lang, cursor, limit)
    return Page[TermOut](items=items, next_cursor=next_cursor)


@router.post("", status_code=201, response_model=TermOut)
async def add_term(body: TermIn, actor: Moderator, session: Session, clock: Now) -> TermOut:
    return await terms.add(session, actor, body, clock.now())


@router.delete("/{term_id}", status_code=204)
async def delete_term(
    term_id: uuid.UUID, actor: Moderator, session: Session, clock: Now
) -> Response:
    await terms.deactivate(session, actor, term_id, clock.now())
    return Response(status_code=204)

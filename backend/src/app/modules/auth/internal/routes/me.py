"""``/v1/me`` and ``/v1/me/sessions`` (05 §D)."""

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.pagination import Page
from app.core.ratelimit import enforce
from app.core.security.actor import Actor
from app.core.security.deps import current_actor
from app.modules.auth.internal.schemas.me import MeOut, MePatchIn, SessionOut
from app.modules.auth.internal.services import me as me_service
from app.modules.auth.internal.services import sessions as sessions_service

router = APIRouter(prefix="/v1/me", tags=["me"])
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]


def tier(name: str) -> Callable[..., Awaitable[Actor]]:
    """The current actor, rate-limited on ``name`` per user."""

    async def dependency(actor: Annotated[Actor, Depends(current_actor)]) -> Actor:
        await enforce(name, {"user": str(actor.user_id)})
        return actor

    return dependency


Reader = Annotated[Actor, Depends(tier("read"))]
Writer = Annotated[Actor, Depends(tier("write"))]


@router.get("", response_model=MeOut)
async def get_me(actor: Reader, session: Session, clock: Now) -> MeOut:
    return await me_service.get_me(session, actor, clock.now())


@router.patch("", response_model=MeOut)
async def patch_me(body: MePatchIn, actor: Writer, session: Session, clock: Now) -> MeOut:
    return await me_service.patch_me(session, actor, body, clock.now())


@router.get("/sessions", response_model=Page[SessionOut])
async def list_sessions(actor: Reader, session: Session) -> Page[SessionOut]:
    rows = await sessions_service.list_live(session, actor)
    items = [
        SessionOut(
            session_id=r.id,
            platform=r.platform,
            app_version=r.app_version,
            model=r.model,
            created_at=r.created_at,
            last_seen_at=r.last_seen_at,
            current=r.id == actor.session_id,
        )
        for r in rows
    ]
    return Page[SessionOut](items=items, next_cursor=None)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: uuid.UUID, actor: Writer, session: Session, clock: Now
) -> Response:
    await sessions_service.revoke_own(session, actor, session_id, clock.now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)

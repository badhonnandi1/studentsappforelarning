"""``/v1/me/profile`` and ``/v1/me/profile/photo`` (05 §D)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.security.actor import Actor
from app.core.security.deps import user_tier
from app.core.storage import Storage, get_storage
from app.modules.auth.internal.schemas.profile import PhotoIn, PhotoOut, ProfileIn, ProfileOut
from app.modules.auth.internal.services import profile as service

router = APIRouter(prefix="/v1/me", tags=["me"])
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]
Reader = Annotated[Actor, Depends(user_tier("read"))]
Writer = Annotated[Actor, Depends(user_tier("write"))]


@router.get("/profile", response_model=ProfileOut)
async def get_profile(actor: Reader, session: Session, clock: Now) -> ProfileOut:
    return await service.get_profile(session, actor, clock.now())


@router.put("/profile", response_model=ProfileOut)
async def put_profile(body: ProfileIn, actor: Writer, session: Session, clock: Now) -> ProfileOut:
    return await service.put_profile(session, actor, body, clock.now())


@router.post("/profile/photo", status_code=202, response_model=PhotoOut)
async def set_photo(
    body: PhotoIn,
    actor: Writer,
    session: Session,
    storage: Annotated[Storage, Depends(get_storage)],
) -> PhotoOut:
    return await service.set_photo(session, actor, body, storage)

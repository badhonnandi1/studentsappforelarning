"""``/v1/me/profile``, photo, privacy and guardian consent (05 §D)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.ratelimit import client_ip
from app.core.security.actor import Actor
from app.core.security.deps import current_actor, user_tier
from app.core.storage import Storage, get_storage
from app.modules.auth.internal.schemas.consent import (
    GuardianConfirmIn,
    GuardianConfirmOut,
    GuardianStartIn,
    GuardianStartOut,
    PrivacyIn,
    PrivacyOut,
)
from app.modules.auth.internal.schemas.profile import PhotoIn, PhotoOut, ProfileIn, ProfileOut
from app.modules.auth.internal.services import consent
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


@router.get("/privacy", response_model=PrivacyOut)
async def get_privacy(actor: Reader, session: Session) -> PrivacyOut:
    return await consent.get_privacy(session, actor)


@router.put("/privacy", response_model=PrivacyOut)
async def put_privacy(body: PrivacyIn, actor: Writer, session: Session) -> PrivacyOut:
    return await consent.put_privacy(session, actor, body)


@router.post("/consent/guardian/start", status_code=202, response_model=GuardianStartOut)
async def start_guardian_consent(
    body: GuardianStartIn,
    request: Request,
    actor: Annotated[Actor, Depends(current_actor)],
    session: Session,
    clock: Now,
) -> GuardianStartOut:
    """T-otp per IP and per guardian number (applied in the service)."""
    challenge_id, expires_at = await consent.start(
        session, actor, body, ip=client_ip(request), now=clock.now()
    )
    return GuardianStartOut(challenge_id=challenge_id, expires_at=expires_at)


@router.post("/consent/guardian/confirm", response_model=GuardianConfirmOut)
async def confirm_guardian_consent(
    body: GuardianConfirmIn, actor: Writer, session: Session, clock: Now
) -> GuardianConfirmOut:
    return await consent.confirm(session, actor, body, clock.now())

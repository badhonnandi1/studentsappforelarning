"""``/v1/me/identities`` and ``/v1/me/phone`` (05 §D, R-25)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.ratelimit import client_ip
from app.core.security.actor import Actor
from app.core.security.deps import user_tier
from app.modules.auth.internal.schemas.social import IdentitiesOut, IdentityOut, LinkIn
from app.modules.auth.internal.schemas.step_up import (
    ChallengeOut,
    PhoneConfirmIn,
    PhoneOut,
    PhoneStartIn,
)
from app.modules.auth.internal.services import phone_change, social_link

router = APIRouter(prefix="/v1/me", tags=["me"])
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]
Reader = Annotated[Actor, Depends(user_tier("read"))]
Writer = Annotated[Actor, Depends(user_tier("write"))]
ProviderName = Annotated[str, Path(pattern=r"^[a-z]{2,20}$")]
StepUpToken = Annotated[str | None, Header(alias="X-Step-Up-Token", max_length=128)]


@router.get("/identities", response_model=IdentitiesOut)
async def list_identities(actor: Reader, session: Session) -> IdentitiesOut:
    return await social_link.list_identities(session, actor)


@router.post(
    "/identities/{provider}", status_code=status.HTTP_201_CREATED, response_model=IdentityOut
)
async def link_identity(
    provider: ProviderName, body: LinkIn, actor: Writer, session: Session, clock: Now
) -> IdentityOut:
    return await social_link.link(session, actor, provider, body, clock.now())


@router.delete("/identities/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_identity(
    provider: ProviderName, actor: Writer, session: Session, clock: Now, step_up: StepUpToken = None
) -> Response:
    await social_link.unlink(session, actor, provider, step_up, clock.now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/phone", response_model=ChallengeOut | PhoneOut)
async def change_phone(
    body: PhoneStartIn | PhoneConfirmIn,
    request: Request,
    response: Response,
    actor: Writer,
    session: Session,
    clock: Now,
    step_up: StepUpToken = None,
) -> ChallengeOut | PhoneOut:
    """Send ``{phone}`` (202, a challenge to the new number), then ``{challenge_id, code}``."""
    if isinstance(body, PhoneConfirmIn):
        return await phone_change.confirm(session, actor, body, clock.now())
    row = await phone_change.start(
        session, actor, body, step_up, ip=client_ip(request), now=clock.now()
    )
    response.status_code = status.HTTP_202_ACCEPTED
    return ChallengeOut(challenge_id=row.id, expires_at=row.expires_at)

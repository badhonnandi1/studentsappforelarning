"""``/v1/auth/otp/*``, ``sign-up/complete``, ``step-up``, ``refresh`` and ``logout``."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.ratelimit import client_ip, rate_limit
from app.core.security.actor import Actor
from app.core.security.deps import current_actor
from app.modules.auth.internal.schemas.auth import (
    NeedsProfileOut,
    OtpSendIn,
    OtpSendOut,
    OtpVerifyIn,
    RefreshIn,
    SignInOut,
    SignUpCompleteIn,
    TokenPair,
)
from app.modules.auth.internal.schemas.step_up import (
    SecondFactorOut,
    StepUpIn,
    StepUpOut,
    StepUpSendIn,
)
from app.modules.auth.internal.services import (
    otp_send,
    otp_verify,
    pending_signup,
    refresh,
    step_up,
)
from app.modules.auth.internal.services import sessions as sessions_service

router = APIRouter(prefix="/v1/auth", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]
AuthTier = [Depends(rate_limit("auth"))]
User = Annotated[Actor, Depends(current_actor)]


@router.post("/otp/send", status_code=status.HTTP_202_ACCEPTED, response_model=OtpSendOut)
async def send_otp(body: OtpSendIn, request: Request, session: Session, clock: Now) -> OtpSendOut:
    row = await otp_send.send_sign_in(session, body, ip=client_ip(request), now=clock.now())
    return OtpSendOut(
        challenge_id=row.id, expires_at=row.expires_at, resend_after_s=otp_send.RESEND_AFTER_S
    )


@router.post(
    "/otp/verify",
    response_model=SignInOut | NeedsProfileOut | SecondFactorOut,
    dependencies=AuthTier,
)
async def verify_otp(
    body: OtpVerifyIn, request: Request, session: Session, clock: Now
) -> SignInOut | NeedsProfileOut | SecondFactorOut:
    return await otp_verify.verify_sign_in(session, body, ip=client_ip(request), now=clock.now())


@router.post(
    "/sign-up/complete",
    status_code=status.HTTP_201_CREATED,
    response_model=TokenPair,
    dependencies=AuthTier,
)
async def complete_sign_up(
    body: SignUpCompleteIn, request: Request, session: Session, clock: Now
) -> TokenPair:
    return await pending_signup.complete(session, body, ip=client_ip(request), now=clock.now())


@router.post(
    "/step-up/send",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=OtpSendOut,
    dependencies=AuthTier,
)
async def send_step_up(
    body: StepUpSendIn, request: Request, actor: User, session: Session, clock: Now
) -> OtpSendOut:
    del body  # the action is bound when the code is checked
    row = await step_up.send(session, actor, ip=client_ip(request), now=clock.now())
    return OtpSendOut(
        challenge_id=row.id, expires_at=row.expires_at, resend_after_s=otp_send.RESEND_AFTER_S
    )


@router.post("/step-up", response_model=StepUpOut, dependencies=AuthTier)
async def verify_step_up(body: StepUpIn, actor: User, session: Session, clock: Now) -> StepUpOut:
    return await step_up.verify(session, actor, body, clock.now())


@router.post("/refresh", response_model=TokenPair, dependencies=AuthTier)
async def refresh_tokens(body: RefreshIn, session: Session, clock: Now) -> TokenPair:
    return await refresh.refresh(session, body.refresh_token, clock.now())


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(actor: User, session: Session, clock: Now) -> Response:
    await sessions_service.logout(session, actor, clock.now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)

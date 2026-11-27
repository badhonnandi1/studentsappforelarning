"""``/v1/auth/social/nonce`` and ``/v1/auth/social/{provider}`` (05 §C.5, §D)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.errors import NotFoundError
from app.core.ratelimit import client_ip, rate_limit
from app.modules.auth.internal.providers import registry
from app.modules.auth.internal.schemas.auth import NeedsProfileOut, SignInOut
from app.modules.auth.internal.schemas.social import NonceIn, NonceOut, SocialSignInIn
from app.modules.auth.internal.services import social_nonce, social_sign_in

router = APIRouter(prefix="/v1/auth/social", tags=["auth"])
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]
AuthTier = [Depends(rate_limit("auth"))]
ProviderName = Annotated[str, Path(pattern=r"^[a-z]{2,20}$")]


@router.post("/nonce", response_model=NonceOut, dependencies=AuthTier)
async def nonce(body: NonceIn, clock: Now) -> NonceOut:
    if not registry.enabled(body.provider):
        raise NotFoundError("This sign-in method is not available")
    value, expires_at = await social_nonce.issue(body.provider, clock.now())
    return NonceOut(nonce=value, expires_at=expires_at)


@router.post("/{provider}", response_model=SignInOut | NeedsProfileOut, dependencies=AuthTier)
async def social(
    provider: ProviderName, body: SocialSignInIn, request: Request, session: Session, clock: Now
) -> SignInOut | NeedsProfileOut:
    return await social_sign_in.sign_in_with(
        session, provider, body, ip=client_ip(request), now=clock.now()
    )

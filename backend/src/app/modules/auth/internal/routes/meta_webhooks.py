"""Facebook data deletion, deletion status and deauthorise (05 §C.5, §D). Signed by Meta."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Path
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.errors import NotFoundError
from app.core.ratelimit import rate_limit
from app.modules.auth.internal.providers import registry
from app.modules.auth.internal.routes.reference import ReadTier
from app.modules.auth.internal.services import meta_callbacks

router = APIRouter(tags=["webhooks"])
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]
SignedRequest = Annotated[str, Form(min_length=3, max_length=8192)]
Limited = [Depends(rate_limit("auth"))]


class DeletionOut(BaseModel):
    url: str
    confirmation_code: str


class DeletionStatusOut(BaseModel):
    status: Literal["received", "completed"]
    completed_at: datetime | None = None


def _enabled() -> None:
    if not registry.enabled("facebook"):
        raise NotFoundError("Not found")


@router.post(
    "/v1/webhooks/facebook/data-deletion", response_model=DeletionOut, dependencies=Limited
)
async def data_deletion(signed_request: SignedRequest, session: Session, clock: Now) -> DeletionOut:
    _enabled()
    url, code = await meta_callbacks.data_deletion(session, signed_request, clock.now())
    return DeletionOut(url=url, confirmation_code=code)


@router.post("/v1/webhooks/facebook/deauthorize", dependencies=Limited)
async def deauthorize(
    signed_request: SignedRequest, session: Session, clock: Now
) -> dict[str, str]:
    _enabled()
    await meta_callbacks.deauthorize(session, signed_request, clock.now())
    return {}


@router.get(
    "/v1/auth/social/facebook/deletion-status/{code}",
    response_model=DeletionStatusOut,
    dependencies=ReadTier,
)
async def deletion_status(
    code: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{8,64}$")], session: Session
) -> DeletionStatusOut:
    status, completed_at = await meta_callbacks.deletion_status(session, code)
    return DeletionStatusOut(status=status, completed_at=completed_at)  # type: ignore[arg-type]

"""Staff SSO (R-07): ``/v1/admin/auth/sso/start`` → IdP → ``/v1/admin/auth/sso/callback``.

The admin web app receives the IdP's redirect and passes ``code`` and ``state`` to the
callback, which returns an admin ``TokenPair``. Both are public and on the auth tier.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.ids import uuid7
from app.core.ratelimit import client_ip, rate_limit
from app.modules.auth.internal.schemas.auth import DeviceId, DeviceInfo, TokenPair
from app.modules.auth.internal.services import staff_sso

router = APIRouter(prefix="/v1/admin/auth/sso", tags=["admin-auth"])
Limited = [Depends(rate_limit("auth"))]


@router.get("/start", status_code=302, response_class=RedirectResponse, dependencies=Limited)
async def start(redirect_uri: Annotated[str, Query(max_length=512)]) -> RedirectResponse:
    url = await staff_sso.start(redirect_uri)
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


@router.get("/callback", response_model=TokenPair, dependencies=Limited)
async def callback(
    request: Request,
    code: Annotated[str, Query(min_length=1, max_length=2048)],
    state: Annotated[str, Query(min_length=16, max_length=256)],
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
    x_device_id: Annotated[DeviceId | None, Header()] = None,
) -> TokenPair:
    """Without ``X-Device-Id`` each sign-in opens its own admin session."""
    device = DeviceInfo(device_id=x_device_id or f"sso-{uuid7().hex}", platform="web")
    return await staff_sso.callback(
        session, code, state, device, ip=client_ip(request), now=clock.now()
    )

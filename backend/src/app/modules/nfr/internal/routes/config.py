"""``GET /v1/config/client``: public client config, edge-cached for 30 s (05 §D)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.ratelimit import client_ip, rate_limit
from app.modules.nfr.internal.schemas.config import ClientConfigOut, KillSwitches, MinAppVersion
from app.modules.nfr.internal.services import runtime_config

router = APIRouter(prefix="/v1/config", tags=["config"])


def _by_ip(request: Request) -> Mapping[str, str]:
    return {"user": f"ip:{client_ip(request)}"}


def to_client_config(values: Mapping[str, Any], clock: Clock) -> ClientConfigOut:
    return ClientConfigOut(
        kill_switches=KillSwitches(
            tutor=values["kill.tutor"],
            photo_solve=values["kill.photo_solve"],
            registrations=values["kill.registrations"],
            payments=values["kill.payments"],
        ),
        min_app_version=MinAppVersion(
            android=values["min_app_version.android"], web=values["min_app_version.web"]
        ),
        support=values["support.links"],
        server_time=clock.now(),
    )


@router.get(
    "/client",
    response_model=ClientConfigOut,
    dependencies=[Depends(rate_limit("read", _by_ip))],
)
async def client_config(
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> ClientConfigOut:
    values = await runtime_config.load_all(session)
    response.headers["Cache-Control"] = "public, max-age=30"
    return to_client_config(values, clock)

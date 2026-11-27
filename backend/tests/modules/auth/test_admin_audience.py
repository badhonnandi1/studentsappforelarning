"""Every ``/v1/admin/*`` route refuses a user token and an admin token without SSO + MFA (R-07)."""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, get_clock
from app.core.db import get_session
from app.core.http import create_app
from app.core.settings import Settings
from app.modules.registry import all_routers
from tests.support.tokens import access_token, bearer, staff_token

pytestmark = [pytest.mark.api, pytest.mark.db]
PUBLIC = {"/v1/admin/auth/sso/start", "/v1/admin/auth/sso/callback"}
_PARAM = re.compile(r"\{[^}]+\}")


@pytest.fixture
async def full_client(
    session: AsyncSession, app_redis: Redis, clock: FrozenClock
) -> AsyncIterator[httpx.AsyncClient]:
    del app_redis
    app = create_app("api", routers=all_routers(), settings=Settings(_env_file=None))

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_clock] = lambda: clock
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.paths = app.openapi()["paths"]  # type: ignore[attr-defined]
        yield c


async def test_admin_routes_need_sso_mfa_tokens(full_client: httpx.AsyncClient) -> None:
    routes = [
        (method.upper(), _PARAM.sub(str(uuid.uuid4()), path))
        for path, operations in full_client.paths.items()  # type: ignore[attr-defined]
        if path.startswith("/v1/admin/") and path not in PUBLIC
        for method in operations
    ]
    assert len(routes) >= 4  # B1: role grants (2), audit log, runtime config; grows later
    user = uuid.uuid4()
    tokens = {
        "user": (access_token(user), 401),
        "no_sso": (staff_token(user, sso=False), 403),
        "no_mfa": (staff_token(user, amr=["pwd"]), 403),
    }
    wrong = []
    for method, path in routes:
        for name, (token, expected) in tokens.items():
            response = await full_client.request(method, path, headers=bearer(token), json={})
            if response.status_code != expected:
                wrong.append((name, method, path, response.status_code))
    assert wrong == []

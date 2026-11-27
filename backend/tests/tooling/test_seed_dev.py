"""``scripts/seed_dev.py``: dev users and identities, a working local admin token, and a hard
refusal outside local and test (no break-glass admin in staging or prod)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Literal

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.http import create_app
from app.core.security import actor as actor_mod
from app.core.security import crypto
from app.core.security.jwt import token_keys
from app.core.settings import Settings
from app.modules import com
from app.modules.auth.internal.models import ExternalIdentity, User
from app.modules.auth.internal.services.rbac import make_grants_loader
from scripts import seed_dev
from tests.support.tokens import bearer, ensure_keys

pytestmark = [pytest.mark.api, pytest.mark.db]
TEST = Settings(_env_file=None, app_env="test")


@pytest.fixture(autouse=True)
async def keys(app_redis: Redis) -> None:
    del app_redis
    await crypto.init_crypto(TEST)
    ensure_keys()


@pytest.fixture
async def client(
    session: AsyncSession, sessions: Callable[[], AsyncSession]
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app("api", routers=com.routers(), settings=TEST)

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    actor_mod.set_grants_loader(make_grants_loader(sessions))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    finally:
        actor_mod.set_grants_loader(None)


async def test_seed_is_idempotent_and_the_token_works(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    first = await seed_dev.seed(session, TEST, now)
    again = await seed_dev.seed(session, TEST, now)
    assert (again.admin_id, again.student_ids, again.social_ids) == (
        first.admin_id, first.student_ids, first.social_ids,
    )  # fmt: skip
    users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    providers = (await session.execute(select(ExternalIdentity.provider))).scalars().all()
    await session.commit()
    assert users == 6
    assert sorted(providers) == ["facebook", "google"]
    claims = token_keys().verify(first.admin_token, audience="admin", now=now)
    assert claims["sso"] is True
    assert "super_admin" in claims["roles"]
    listed = await client.get("/v1/admin/moderation/terms", headers=bearer(again.admin_token))
    assert listed.status_code == 200, listed.text


@pytest.mark.parametrize("env", ["staging", "prod"])
async def test_refuses_outside_local_and_test(
    session: AsyncSession, env: Literal["staging", "prod"]
) -> None:
    settings = Settings.model_construct(app_env=env)
    with pytest.raises(seed_dev.DevOnlyError, match=env):
        await seed_dev.seed(session, settings, datetime.now(UTC))
    users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
    await session.commit()
    assert users == 0

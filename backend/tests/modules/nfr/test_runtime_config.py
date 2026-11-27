"""Runtime config: allow-list, validation, caches, kill switches, ``/v1/config/client``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.db import get_session
from app.core.errors import UnavailableError, ValidationAppError
from app.core.http import create_app
from app.core.redis import set_json, use_client
from app.core.settings import Settings
from app.modules.nfr import routers
from app.modules.nfr.internal.services import runtime_config as rc

pytestmark = [pytest.mark.db, pytest.mark.integration]


async def test_defaults_then_set_and_invalidate(session: AsyncSession, app_redis: Redis) -> None:
    assert (await rc.load_all(session))["kill.tutor"] is False
    async with session.begin():
        before, after = await rc.set_value(session, "kill.tutor", True, actor_id=None, now=rc_now())
    assert (before, after) == (False, True)
    assert await rc.is_killed(session, "tutor") is False  # still cached
    await rc.invalidate()
    assert await rc.is_killed(session, "tutor") is True
    with pytest.raises(UnavailableError) as raised:
        await rc.require_enabled(session, "tutor")
    assert raised.value.code == "kill_switch"
    await rc.require_enabled(session, "payments")


def rc_now() -> datetime:
    return datetime(2026, 1, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("kill.everything", True),
        ("kill.tutor", "maybe"),
        ("min_app_version.android", "1.2"),
        ("ratelimit.overrides", {"nope": [{"scope": "user", "limit": 1, "window_s": 60}]}),
        ("ratelimit.overrides", {"read": [{"scope": "user"}]}),
    ],
)
def test_invalid_writes_are_refused(key: str, value: object) -> None:
    with pytest.raises(ValidationAppError):
        rc.validate(key, value)


async def test_rate_limit_overrides_apply(session: AsyncSession, app_redis: Redis) -> None:
    rule = {"read": [{"scope": "user", "limit": 1, "window_s": 60}]}
    async with session.begin():
        await rc.set_value(session, "ratelimit.overrides", rule, actor_id=None, now=rc_now())
    await rc.invalidate()
    await rc.load_all(session)
    assert ratelimit.get_tier("read").rules[0].limit == 1


async def test_redis_cache_and_fallback(session: AsyncSession, app_redis: Redis) -> None:
    await set_json(rc.CACHE_KEY, {"kill.photo_solve": True}, 30)
    assert await rc.get_value(session, "kill.photo_solve") is True
    with pytest.raises(KeyError):
        await rc.get_value(session, "kill.nothing")
    use_client(Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2))
    rc._cache = None
    assert (await rc.load_all(session))["kill.photo_solve"] is False  # straight from Postgres
    await rc.invalidate()


@pytest.fixture
async def client(session: AsyncSession, app_redis: Redis) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app("api", routers=routers(), settings=Settings(_env_file=None))

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.api
async def test_client_config_route(client: httpx.AsyncClient) -> None:
    response = await client.get("/v1/config/client")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "public, max-age=30"
    body = response.json()
    assert body["kill_switches"] == {
        "tutor": False,
        "photo_solve": False,
        "registrations": False,
        "payments": False,
    }
    assert body["min_app_version"] == {"android": "1.0.0", "web": "1.0.0"}
    assert body["support"] == {}
    assert "server_time" in body

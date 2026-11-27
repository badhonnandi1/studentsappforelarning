"""Actor permissions, grants cache, session revocation and the auth dependencies."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Annotated

import httpx
import pytest
from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.errors import ForbiddenError
from app.core.http import create_app
from app.core.redis import use_client
from app.core.security import actor as actor_mod
from app.core.security.actor import Actor, Grant, can, require
from app.core.security.deps import admin_actor, current_actor, staff_permission
from app.core.security.jwt import token_keys
from app.core.settings import Settings
from tests.support.tokens import TTL, access_token, bearer, ensure_keys, staff_token

pytestmark = pytest.mark.api
USER = uuid.UUID("00000000-0000-7000-8000-00000000000a")
SUBJECT = uuid.UUID("00000000-0000-7000-8000-0000000000b1")
loaded: list[uuid.UUID] = []


async def fake_loader(user_id: uuid.UUID) -> list[Grant]:
    loaded.append(user_id)
    return [Grant("audit.read"), Grant("content.publish", "subject", SUBJECT)]


@pytest.fixture(autouse=True)
def loader() -> Iterator[None]:
    loaded.clear()
    actor_mod.set_grants_loader(fake_loader)
    yield
    actor_mod.set_grants_loader(None)


def make(*roles: str, grants: tuple[Grant, ...] = ()) -> Actor:
    return Actor(USER, uuid.uuid4(), frozenset(roles), grants=grants)


def test_can_checks_permission_and_scope() -> None:
    a = make(grants=(Grant("audit.read"), Grant("content.publish", "subject", SUBJECT)))
    assert can(a, "audit.read")
    assert can(a, "audit.read", "tenant", uuid.uuid4())  # global grants cover every scope
    assert can(a, "content.publish", "subject", SUBJECT)
    assert not can(a, "content.publish", "subject", uuid.uuid4())
    assert not can(a, "content.publish")
    with pytest.raises(ForbiddenError):
        require(a, "ops.config")


def test_super_admin_passes_every_check() -> None:
    assert can(make("super_admin"), "anything.at_all")


async def test_grants_cached_and_invalidated(app_redis: Redis) -> None:
    first = await actor_mod.load_grants(USER)
    again = await actor_mod.load_grants(USER)
    assert first == again
    assert loaded == [USER]
    assert await app_redis.ttl(actor_mod.grants_key(USER)) > 0
    await actor_mod.invalidate_grants(USER)
    await actor_mod.load_grants(USER)
    assert loaded == [USER, USER]


async def test_no_loader_means_no_grants(app_redis: Redis) -> None:
    actor_mod.set_grants_loader(None)
    assert await actor_mod.load_grants(USER) == ()


@pytest.fixture
def dead_redis() -> Iterator[None]:
    use_client(Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2))
    yield
    use_client(None)


@pytest.mark.usefixtures("dead_redis")
async def test_redis_down_falls_back_and_revocation_policy() -> None:
    assert len(await actor_mod.load_grants(USER)) == 2
    sid = uuid.uuid4()
    assert await actor_mod.is_session_revoked(sid, fail_closed=False) is False
    assert await actor_mod.is_session_revoked(sid, fail_closed=True) is True
    with pytest.raises((RedisConnectionError, OSError)):
        await actor_mod.invalidate_grants(USER)


def build_app() -> httpx.AsyncClient:
    router = APIRouter()

    @router.get("/me")
    async def me(a: Annotated[Actor, Depends(current_actor)]) -> dict[str, object]:
        return {"user": str(a.user_id), "grants": len(a.grants)}

    @router.get("/admin")
    async def admin(a: Annotated[Actor, Depends(admin_actor)]) -> dict[str, str]:
        return {"user": str(a.user_id)}

    @router.get("/config")
    async def config(
        _: Annotated[Actor, Depends(staff_permission("ops.config"))],
    ) -> dict[str, str]:
        return {}

    @router.get("/audit")
    async def audit(_: Annotated[Actor, Depends(staff_permission("audit.read"))]) -> dict[str, str]:
        return {}

    app = create_app("api", routers=[router], settings=Settings(_env_file=None))
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


@pytest.fixture
async def client(app_redis: Redis) -> AsyncIterator[httpx.AsyncClient]:
    async with build_app() as c:
        yield c


async def test_current_actor(client: httpx.AsyncClient, app_redis: Redis) -> None:
    sid = uuid.uuid4()
    token = access_token(USER, session_id=sid)
    ok = await client.get("/me", headers=bearer(token))
    assert ok.json() == {"user": str(USER), "grants": 2}
    assert (await client.get("/me")).status_code == 401
    assert (await client.get("/me", headers={"Authorization": "Basic x"})).status_code == 401
    admin_token = staff_token(USER)
    assert (await client.get("/me", headers=bearer(admin_token))).status_code == 401
    await app_redis.set(actor_mod.revoked_key(sid), "1")
    revoked = await client.get("/me", headers=bearer(token))
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "session_revoked"


async def test_bad_subject_claim_is_unauthorized(client: httpx.AsyncClient) -> None:
    ensure_keys()
    token = token_keys().sign(
        {"sub": "not-a-uuid", "sid": "x"}, audience="api", now=datetime.now(UTC), ttl=TTL
    )
    assert (await client.get("/me", headers=bearer(token))).status_code == 401


async def test_admin_requires_sso_and_mfa(client: httpx.AsyncClient) -> None:
    assert (await client.get("/admin", headers=bearer(staff_token(USER)))).status_code == 200
    no_mfa = staff_token(USER, amr=["pwd"])
    no_sso = staff_token(USER, sso=False)
    for token in (no_mfa, no_sso):
        response = await client.get("/admin", headers=bearer(token))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "mfa_required"
    user = access_token(USER)
    assert (await client.get("/admin", headers=bearer(user))).status_code == 401


async def test_staff_permission(client: httpx.AsyncClient) -> None:
    token = staff_token(USER)
    assert (await client.get("/audit", headers=bearer(token))).status_code == 200
    assert (await client.get("/config", headers=bearer(token))).status_code == 403
    boss = staff_token(USER, roles=["super_admin"])
    assert (await client.get("/config", headers=bearer(boss))).status_code == 200

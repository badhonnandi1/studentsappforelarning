"""``GET /v1/admin/audit-log`` and ``PUT /v1/admin/runtime-config/{key}``."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.http import create_app
from app.core.security.actor import Actor
from app.core.settings import Settings
from app.modules import nfr, ops
from app.modules.ops.internal.models import AuditLog
from tests.modules.ops.conftest import AUDITOR, OPERATOR
from tests.support.tokens import bearer, staff_token
from tests.support.users import make_user

pytestmark = [pytest.mark.api, pytest.mark.db]


@pytest.fixture
async def client(session: AsyncSession, app_redis: Redis) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app("api", routers=ops.routers(), settings=Settings(_env_file=None))

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def as_(user: uuid.UUID) -> dict[str, str]:
    return bearer(staff_token(user))


async def seed(session: AsyncSession, n: int, *, actor: uuid.UUID = AUDITOR) -> None:
    staff = Actor(actor, uuid.uuid4(), frozenset({"reviewer"}), audience="admin")
    base = datetime.now(UTC) - timedelta(hours=1)
    async with session.begin():
        for i in range(n):
            target = ops.AuditTarget(type="question", id=f"q-{i}")
            async with ops.audited(
                session, staff, "content.question.update", target, now=base + timedelta(seconds=i)
            ):
                pass


async def test_put_runtime_config_writes_and_audits(
    client: httpx.AsyncClient, session: AsyncSession, sessions: Callable[[], AsyncSession]
) -> None:
    async with sessions() as setup, setup.begin():  # updated_by references identity.users
        await make_user(setup, OPERATOR)
    body = {"value": True, "reason": "SMS provider outage"}
    response = await client.put(
        "/v1/admin/runtime-config/kill.tutor", json=body, headers=as_(OPERATOR)
    )
    assert response.status_code == 200
    assert response.json()["key"] == "kill.tutor"
    assert response.json()["value"] is True
    assert await nfr.get_runtime_flag(session, "kill.tutor") is True
    row = (await session.execute(select(AuditLog))).scalar_one()
    assert row.action == "ops.runtime_config.update"
    assert (row.target_type, row.target_id) == ("runtime_config", "kill.tutor")
    assert (row.before, row.after) == ({"value": False}, {"value": True})
    assert row.reason == "SMS provider outage"
    assert row.ip_hash is not None
    assert row.request_id


async def test_put_runtime_config_rejects(client: httpx.AsyncClient, session: AsyncSession) -> None:
    body = {"value": "yes please", "reason": "testing"}
    bad = await client.put("/v1/admin/runtime-config/kill.tutor", json=body, headers=as_(OPERATOR))
    assert bad.status_code == 422
    unknown = await client.put(
        "/v1/admin/runtime-config/kill.nope",
        json={"value": 1, "reason": "x" * 5},
        headers=as_(OPERATOR),
    )
    assert unknown.status_code == 422
    denied = await client.put(
        "/v1/admin/runtime-config/kill.tutor",
        json={"value": True, "reason": "abc"},
        headers=as_(AUDITOR),
    )
    assert denied.status_code == 403
    assert (await session.execute(select(AuditLog))).first() is None


async def test_audit_search_pages_newest_first(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    await seed(session, 5)
    first = await client.get("/v1/admin/audit-log", params={"limit": 2}, headers=as_(AUDITOR))
    assert first.status_code == 200
    page = first.json()
    assert [i["target_id"] for i in page["items"]] == ["q-4", "q-3"]
    seen = [i["target_id"] for i in page["items"]]
    cursor = page["next_cursor"]
    while cursor:
        more = await client.get(
            "/v1/admin/audit-log", params={"limit": 2, "cursor": cursor}, headers=as_(AUDITOR)
        )
        seen += [i["target_id"] for i in more.json()["items"]]
        cursor = more.json()["next_cursor"]
    assert seen == ["q-4", "q-3", "q-2", "q-1", "q-0"]


async def test_audit_search_filters(client: httpx.AsyncClient, session: AsyncSession) -> None:
    await seed(session, 2)
    await seed(session, 1, actor=OPERATOR)
    params = {
        "actor_user_id": str(OPERATOR),
        "target_type": "question",
        "target_id": "q-0",
        "action": "content.question.update",
    }
    found = await client.get("/v1/admin/audit-log", params=params, headers=as_(AUDITOR))
    assert [i["actor_user_id"] for i in found.json()["items"]] == [str(OPERATOR)]
    old = {"from": "2020-01-01T00:00:00Z", "to": "2020-01-02T00:00:00Z"}
    assert (await client.get("/v1/admin/audit-log", params=old, headers=as_(AUDITOR))).json()[
        "items"
    ] == []


@pytest.mark.parametrize(
    "params",
    [
        {"from": "2026-01-01T00:00:00Z", "to": "2026-06-01T00:00:00Z"},
        {"from": "2026-02-01T00:00:00Z", "to": "2026-01-01T00:00:00Z"},
        {"cursor": "bm9wZQ"},
        {"cursor": "WyJub3QtYS1kYXRlIiwieCJd"},
        {"limit": 101},
    ],
)
async def test_audit_search_rejects(
    client: httpx.AsyncClient, params: dict[str, str | int]
) -> None:
    response = await client.get("/v1/admin/audit-log", params=params, headers=as_(AUDITOR))
    assert response.status_code == 422


async def test_audit_search_needs_staff_sso(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/admin/audit-log")).status_code == 401
    stranger = bearer(staff_token(uuid.uuid4()))
    assert (await client.get("/v1/admin/audit-log", headers=stranger)).status_code == 403

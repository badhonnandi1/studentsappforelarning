"""RBAC: the grants loader, ``can()`` scopes, and audited role grants (05 §C.6, §D)."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import httpx
import pytest
import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import actor as actor_mod
from app.core.security.actor import Actor, Grant, can
from app.modules.auth.internal.models import (
    DeviceSession,
    Role,
    RoleGrant,
    RolePermission,
    User,
)
from app.modules.auth.internal.schemas.auth import DeviceInfo
from app.modules.auth.internal.services import rbac, sign_in
from app.modules.ops.internal.models import AuditLog
from tests.support.tokens import bearer, staff_token
from tests.support.users import grant_role, make_user

pytestmark = [pytest.mark.api, pytest.mark.db]
URL = "/v1/admin/role-grants"
NOW = datetime(2026, 11, 27, 6, 0, tzinfo=UTC)
SubjectId = uuid.UUID("00000000-0000-7000-8000-00000000c0de")


@pytest.fixture(autouse=True)
def db_grants(sessions: Callable[[], AsyncSession]) -> Iterator[None]:
    actor_mod.set_grants_loader(rbac.make_grants_loader(sessions))
    yield
    actor_mod.set_grants_loader(None)


async def staff(sessions: Callable[[], AsyncSession], *roles: str) -> dict[str, str]:
    async with sessions() as s, s.begin():
        user = await make_user(s)
        for role in roles:
            await grant_role(s, user.id, role)
    return bearer(staff_token(user.id, roles=roles))


async def target(sessions: Callable[[], AsyncSession]) -> uuid.UUID:
    async with sessions() as s, s.begin():
        return (await make_user(s)).id


def body(user_id: uuid.UUID, role: str = "ops_admin", **extra: object) -> dict[str, object]:
    return {"user_id": str(user_id), "role_code": role, "reason": "on-call rota", **extra}


def test_can_scopes() -> None:
    subject = Grant("content.author", "subject", SubjectId)
    who = Actor(uuid.uuid4(), uuid.uuid4(), frozenset(), grants=(Grant("user.read"), subject))
    assert can(who, "user.read", "tenant", uuid.uuid4())  # global covers every scope
    assert can(who, "content.author", "subject", SubjectId)
    assert not can(who, "content.author", "subject", uuid.uuid4())
    assert not can(who, "content.author")
    assert not can(who, "content.author", "tenant", SubjectId)


async def test_loader_reads_seeded_role_permissions(sessions: Callable[[], AsyncSession]) -> None:
    user_id = await target(sessions)
    async with sessions() as s, s.begin():
        await grant_role(s, user_id, "reviewer", scope_type="subject", scope_id=SubjectId)
    grants = await rbac.make_grants_loader(sessions)(user_id)
    assert {g.permission for g in grants} == {"content.read", "content.verify", "content.triage"}
    assert all(g.scope_id == SubjectId for g in grants)


async def test_super_admin_grants_and_is_logged(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    headers = await staff(sessions, "super_admin")
    user_id = await target(sessions)
    with structlog.testing.capture_logs() as logs:
        created = await client.post(URL, json=body(user_id), headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["role_code"] == "ops_admin"
    assert any(e["event"] == "rbac_super_admin_bypass" for e in logs)
    async with sessions() as s:
        audit = await s.execute(select(AuditLog).where(AuditLog.action == "auth.role.grant"))
        row = audit.scalar_one()
        assert row.reason == "on-call rota"
        assert row.after is not None
        assert row.after["role_code"] == "ops_admin"
    duplicate = await client.post(URL, json=body(user_id), headers=headers)
    assert duplicate.status_code == 409


@pytest.mark.parametrize(
    ("payload", "status"),
    [
        ({"role": "astronaut"}, 422),
        ({"scope_type": "subject"}, 422),
        ({"scope_id": str(SubjectId)}, 422),
        ({"reason": ""}, 422),
    ],
)
async def test_grant_validation(
    client: httpx.AsyncClient,
    sessions: Callable[[], AsyncSession],
    payload: dict[str, str],
    status: int,
) -> None:
    headers = await staff(sessions, "super_admin")
    request = body(await target(sessions), payload.pop("role", "ops_admin"), **payload)
    assert (await client.post(URL, json=request, headers=headers)).status_code == status


async def test_unknown_user_and_missing_permission(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    root = await staff(sessions, "super_admin")
    assert (await client.post(URL, json=body(uuid.uuid4()), headers=root)).status_code == 404
    ops_admin = await staff(sessions, "ops_admin")  # holds no role.grant
    refused = await client.post(URL, json=body(await target(sessions)), headers=ops_admin)
    assert refused.status_code == 403


async def test_cannot_grant_above_own_role(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    async with sessions() as s, s.begin():
        s.add(Role(code="grant_clerk", name_bn="ক", name_en="Grant clerk", is_staff=True))
        await s.flush()
        for code in ("role.grant", "content.read", "content.author"):
            s.add(RolePermission(role_code="grant_clerk", permission_code=code))
    headers = await staff(sessions, "grant_clerk")
    user_id = await target(sessions)
    for role in ("ops_admin", "super_admin", "reviewer"):
        refused = await client.post(URL, json=body(user_id, role), headers=headers)
        assert refused.status_code == 403
        assert refused.json()["error"]["code"] == "role_above_own"
    allowed = await client.post(URL, json=body(user_id, "content_author"), headers=headers)
    assert allowed.status_code == 201


async def test_revoke_invalidates_cache_and_ends_admin_sessions(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession], app_redis: Redis
) -> None:
    headers = await staff(sessions, "super_admin")
    user_id = await target(sessions)
    async with sessions() as s, s.begin():
        grant = await grant_role(s, user_id, "ops_admin")
    async with sessions() as s, s.begin():
        member = await s.get(User, user_id)
        assert member is not None
        web = DeviceInfo(device_id="device-admin", platform="web")
        started = await sign_in.start_session(
            s, member, "sso", web, ip=None, now=NOW, audience="admin"
        )
    assert await actor_mod.load_grants(user_id)  # fills the cache
    assert await app_redis.exists(actor_mod.grants_key(user_id))
    assert (await client.delete(f"{URL}/{grant.id}", headers=headers)).status_code == 204
    assert not await app_redis.exists(actor_mod.grants_key(user_id))
    assert await app_redis.exists(actor_mod.revoked_key(started.session.id))
    async with sessions() as s:
        ds = await s.get(DeviceSession, started.session.id)
        assert ds is not None
        assert ds.revoke_reason == "admin"
        revoked = await s.get(RoleGrant, grant.id)
        assert revoked is not None
        assert revoked.revoked_at is not None
    assert (await client.delete(f"{URL}/{grant.id}", headers=headers)).status_code == 404

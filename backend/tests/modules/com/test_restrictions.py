"""Mute and ban: a ban revokes sessions and refuses sign-in; a mute blocks reports; lifting
restores; every write is audited (05 §E)."""

from __future__ import annotations

import uuid
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.errors import ForbiddenError
from app.core.redis import use_client
from app.modules import com
from app.modules.auth.internal.models import DeviceSession, RefreshToken
from app.modules.com.internal.models import UserRestriction
from app.modules.com.internal.services import restrictions
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.test_providers_edge import redis_down
from tests.modules.com.conftest import OUTSIDER, as_staff, signed_in
from tests.support.tokens import bearer
from tests.support.users import make_user

pytestmark = [pytest.mark.api, pytest.mark.db, pytest.mark.usefixtures("staff")]
URL = "/v1/admin/moderation/restrictions"
REPORT = {"target_type": "post", "target_id": str(uuid.uuid4()), "reason": "spam"}


@pytest.fixture
async def student(session: AsyncSession) -> uuid.UUID:
    async with session.begin():
        return (await make_user(session)).id


async def restrict(
    client: httpx.AsyncClient, user_id: uuid.UUID, kind: str, scope: str = "all", **extra: object
) -> httpx.Response:
    body = {
        "user_id": str(user_id),
        "kind": kind,
        "scope": scope,
        "reason": "Repeated abuse",
        **extra,
    }
    headers = {**as_staff(), "Idempotency-Key": str(uuid.uuid4())}
    return await client.post(URL, json=body, headers=headers)


async def audit_actions(session: AsyncSession) -> list[tuple[str, dict[str, object] | None]]:
    rows = (await session.execute(select(AuditLog.action, AuditLog.after))).all()
    await session.commit()
    return [(r[0], r[1]) for r in rows if r[0].startswith("com.")]


async def test_ban_revokes_sessions_and_refuses_sign_in(
    client: httpx.AsyncClient, session: AsyncSession, student: uuid.UUID, clock: FrozenClock
) -> None:
    token = await signed_in(session, student, clock.now())
    await signed_in(session, student, clock.now(), device="device-c002")
    assert (await client.post("/v1/reports", json=REPORT, headers=bearer(token))).status_code == 201
    banned = await restrict(client, student, "ban")
    assert banned.status_code == 201, banned.text
    assert banned.json()["scope"] == "all"
    sessions = (await session.execute(select(DeviceSession))).scalars().all()
    refresh = (await session.execute(select(RefreshToken.revoked_at))).scalars().all()
    await session.commit()
    assert {(s.revoke_reason, s.revoked_at is not None) for s in sessions} == {("admin", True)}
    assert all(r is not None for r in refresh)
    again = await client.post("/v1/reports", json=REPORT, headers=bearer(token))
    assert again.status_code == 401
    with pytest.raises(ForbiddenError) as err:
        await signed_in(session, student, clock.now(), device="device-c003")
    assert err.value.code == "account_banned"
    ban = [
        after for action, after in await audit_actions(session) if action == "com.restriction.ban"
    ]
    assert ban[0] is not None
    assert ban[0]["sessions_revoked"] == 2


async def test_create_is_idempotent(
    client: httpx.AsyncClient, session: AsyncSession, student: uuid.UUID
) -> None:
    body = {"user_id": str(student), "kind": "mute", "scope": "community", "reason": "Spamming"}
    headers = {**as_staff(), "Idempotency-Key": str(uuid.uuid4())}
    first = await client.post(URL, json=body, headers=headers)
    second = await client.post(URL, json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert second.headers["Idempotent-Replay"] == "true"
    assert second.json() == first.json()
    count = len((await session.execute(select(UserRestriction))).scalars().all())
    await session.commit()
    assert count == 1
    no_key = await client.post(URL, json=body, headers=as_staff())
    assert no_key.status_code == 422


async def test_mute_blocks_reports_and_lift_restores(
    client: httpx.AsyncClient, session: AsyncSession, student: uuid.UUID, clock: FrozenClock
) -> None:
    token = await signed_in(session, student, clock.now())
    muted = await restrict(client, student, "mute", "community")
    refused = await client.post("/v1/reports", json=REPORT, headers=bearer(token))
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "restricted"
    assert await com.is_restricted(session, student, "community", clock.now())
    assert not await com.is_banned(session, student, clock.now())
    lifted = await client.delete(f"{URL}/{muted.json()['id']}", headers=as_staff())
    assert lifted.status_code == 204
    assert (
        await client.delete(f"{URL}/{muted.json()['id']}", headers=as_staff())
    ).status_code == 404
    allowed = await client.post("/v1/reports", json=REPORT, headers=bearer(token))
    assert allowed.status_code == 201
    actions = [action for action, _ in await audit_actions(session)]
    assert actions == ["com.restriction.mute", "com.restriction.lift", "com.report.create"]


async def test_scoped_ban_ends_sessions_but_allows_sign_in(
    client: httpx.AsyncClient, session: AsyncSession, student: uuid.UUID, clock: FrozenClock
) -> None:
    token = await signed_in(session, student, clock.now())
    assert (await restrict(client, student, "ban", "profile")).status_code == 201
    assert (await client.post("/v1/reports", json=REPORT, headers=bearer(token))).status_code == 401
    fresh = await signed_in(session, student, clock.now(), device="device-c009")
    assert (await client.post("/v1/reports", json=REPORT, headers=bearer(fresh))).status_code == 201
    assert await com.is_restricted(session, student, "profile", clock.now(), kind="ban")
    assert not await com.is_restricted(session, student, "community", clock.now())


async def test_timed_restriction_expires(
    client: httpx.AsyncClient, session: AsyncSession, student: uuid.UUID, clock: FrozenClock
) -> None:
    ends = (clock.now() + timedelta(hours=1)).isoformat()
    assert (await restrict(client, student, "mute", ends_at=ends)).status_code == 201
    assert await com.is_restricted(session, student, "community", clock.now())
    clock.advance(hours=2)
    assert not await com.is_restricted(session, student, "community", clock.now())


async def test_rejections(
    client: httpx.AsyncClient, session: AsyncSession, student: uuid.UUID, clock: FrozenClock
) -> None:
    past = (clock.now() - timedelta(minutes=1)).isoformat()
    assert (await restrict(client, student, "mute", ends_at=past)).status_code == 422
    assert (await restrict(client, uuid.uuid4(), "ban")).status_code == 404
    assert (await restrict(client, student, "mute", reason="x")).status_code == 422
    assert (await client.delete(f"{URL}/{uuid.uuid4()}", headers=as_staff())).status_code == 404
    outsider = await client.post(URL, json={}, headers=as_staff(OUTSIDER))
    assert outsider.status_code == 403
    count = len((await session.execute(select(UserRestriction))).scalars().all())
    await session.commit()
    assert count == 0


async def test_redis_down_reads_postgres(
    client: httpx.AsyncClient, session: AsyncSession, student: uuid.UUID, clock: FrozenClock
) -> None:
    assert (await restrict(client, student, "ban")).status_code == 201
    redis_down()
    try:
        assert await com.is_banned(session, student, clock.now())
        await restrictions.after_commit(student, [])  # a failed invalidation is only logged
    finally:
        use_client(None)


def test_a_ban_needs_a_registered_revoker() -> None:
    com.set_session_revoker(None)
    with pytest.raises(RuntimeError, match="SessionRevoker"):
        restrictions.revoker()

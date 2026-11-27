"""Refresh rotation, reuse detection, logout, device sessions (05 §C.4)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.settings import get_settings
from app.modules.auth.internal.models import DeviceSession, RefreshToken
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.conftest import auth_header, sign_in, sign_up

pytestmark = [pytest.mark.api, pytest.mark.db]


async def refresh(client: httpx.AsyncClient, token: str) -> httpx.Response:
    return await client.post("/v1/auth/refresh", json={"refresh_token": token})


async def test_refresh_rotates_within_the_family(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession], clock: FrozenClock
) -> None:
    pair = await sign_up(client)
    clock.advance(minutes=1)
    rotated = await refresh(client, pair["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    new = rotated.json()
    assert new["refresh_token"] != pair["refresh_token"]
    assert new["session_id"] == pair["session_id"]
    assert (await client.get("/v1/me", headers=auth_header(new))).status_code == 200
    async with sessions() as check:
        rows = (await check.execute(select(RefreshToken).order_by(RefreshToken.issued_at))).all()
        tokens = [r[0] for r in rows]
        assert len({t.family_id for t in tokens}) == 1
        assert tokens[0].rotated_at is not None
        assert tokens[1].parent_id == tokens[0].id


async def test_reuse_revokes_family_and_session(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession], app_redis: Redis
) -> None:
    pair = await sign_up(client)
    new = (await refresh(client, pair["refresh_token"])).json()
    replay = await refresh(client, pair["refresh_token"])
    assert replay.status_code == 401
    assert (await refresh(client, new["refresh_token"])).status_code == 401
    assert await app_redis.exists(f"revoked_sess:{pair['session_id']}")
    me = await client.get("/v1/me", headers=auth_header(new))
    assert me.status_code == 401
    assert me.json()["error"]["code"] == "session_revoked"
    async with sessions() as check:
        ds = (await check.execute(select(DeviceSession))).scalar_one()
        assert ds.revoke_reason == "token_reuse"
        tokens = (await check.execute(select(RefreshToken))).scalars().all()
        assert all(t.revoked_at is not None for t in tokens)
        actions = (await check.execute(select(AuditLog.action))).scalars().all()
        assert "auth.refresh.reuse" in actions


async def test_expired_and_unknown_refresh(client: httpx.AsyncClient, clock: FrozenClock) -> None:
    pair = await sign_up(client)
    assert (await refresh(client, "x" * 43)).status_code == 401
    clock.advance(days=31)
    expired = await refresh(client, pair["refresh_token"])
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "token_expired"


async def test_refresh_slides_thirty_days(client: httpx.AsyncClient, clock: FrozenClock) -> None:
    pair = await sign_up(client)
    for _ in range(3):
        clock.advance(days=20)
        response = await refresh(client, pair["refresh_token"])
        assert response.status_code == 200
        pair = response.json()


async def test_logout_revokes_the_session(client: httpx.AsyncClient, app_redis: Redis) -> None:
    pair = await sign_up(client)
    assert (await client.post("/v1/auth/logout", headers=auth_header(pair))).status_code == 204
    assert await app_redis.exists(f"revoked_sess:{pair['session_id']}")
    assert (await client.get("/v1/me", headers=auth_header(pair))).status_code == 401
    assert (await refresh(client, pair["refresh_token"])).status_code == 401
    assert (await client.post("/v1/auth/logout")).status_code == 401


async def test_same_device_reuses_session_and_ends_old_tokens(client: httpx.AsyncClient) -> None:
    first = await sign_up(client)
    second = await sign_in(client)
    assert second["session_id"] == first["session_id"]
    assert (await refresh(client, first["refresh_token"])).status_code == 401
    assert (await refresh(client, second["refresh_token"])).status_code == 401  # family reuse


async def test_session_cap_evicts_oldest(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch, app_redis: Redis
) -> None:
    monkeypatch.setattr(get_settings(), "max_sessions_per_user", 2)
    oldest = await sign_up(client, device_id="device-cap-1")
    await sign_in(client, device_id="device-cap-2")
    await sign_in(client, device_id="device-cap-3")
    assert await app_redis.exists(f"revoked_sess:{oldest['session_id']}")
    listed = await client.get("/v1/me/sessions", headers=auth_header(oldest))
    assert listed.status_code == 401

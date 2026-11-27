"""AUTH fixtures: an API client on the rolled-back session, a frozen clock, fake SMS."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, get_clock
from app.core.db import get_session
from app.core.http import create_app
from app.core.security import crypto
from app.core.settings import Settings
from app.core.storage import Storage, get_storage
from app.modules import auth
from app.modules.auth.internal.providers import captcha
from app.modules.plan.internal import providers
from app.modules.plan.internal.providers.sms_fake import FakeSmsGateway
from app.modules.plan.internal.services import templates
from tests.support.tokens import ensure_keys

UPLOADS = "sp-test-uploads"
TEST_CODE = "123456"  # TEST_PHONE_OTP in tests/conftest.py
PHONE = "+8801700000001"  # reserved test block (R-31)
DEVICE: dict[str, Any] = {"device_id": "device-0001", "platform": "android", "app_version": "1.0.0"}


@pytest.fixture(autouse=True)
async def field_crypto() -> None:
    await crypto.init_crypto(Settings(_env_file=None))
    ensure_keys()


@pytest.fixture(autouse=True)
def fake_sms() -> Iterator[FakeSmsGateway]:
    fake = FakeSmsGateway(Settings(_env_file=None))
    providers.use_gateway(fake)
    templates.clear_cache()
    captcha.use_verifier(None)
    yield fake
    providers.use_gateway(None)
    templates.clear_cache()


def uploads_storage() -> Storage:
    return Storage(Settings(_env_file=None, s3_bucket_uploads=UPLOADS))


@pytest.fixture
def clock() -> FrozenClock:
    """SMS partitions exist from the current month onward."""
    return FrozenClock(datetime.now(UTC))


@pytest.fixture
async def client(
    session: AsyncSession, app_redis: Redis, clock: FrozenClock
) -> AsyncIterator[httpx.AsyncClient]:
    del app_redis
    app = create_app("api", routers=auth.routers(), settings=Settings(_env_file=None))

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_storage] = lambda: uploads_storage()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def send(
    client: httpx.AsyncClient, phone: str = PHONE, *, device: str = "device-0001", **extra: Any
) -> httpx.Response:
    body = {"phone": phone, "device_id": device, **extra}
    return await client.post("/v1/auth/otp/send", json=body)


async def verify(
    client: httpx.AsyncClient, challenge_id: str, code: str = TEST_CODE, **device: Any
) -> httpx.Response:
    body = {"challenge_id": challenge_id, "code": code, "device": {**DEVICE, **device}}
    return await client.post("/v1/auth/otp/verify", json=body)


async def sign_up(
    client: httpx.AsyncClient, phone: str = PHONE, *, dob: str = "2000-01-01", **device: Any
) -> dict[str, Any]:
    """Send → verify → complete sign-up; return the ``TokenPair`` JSON."""
    sent = await send(client, phone, device=device.get("device_id", DEVICE["device_id"]))
    pending = await verify(client, sent.json()["challenge_id"], **device)
    assert pending.json()["status"] == "needs_profile", pending.text
    token = pending.json()["pending_signup_token"]
    body = {"pending_signup_token": token, "date_of_birth": dob}
    done = await client.post("/v1/auth/sign-up/complete", json=body)
    assert done.status_code == 201, done.text
    return dict(done.json())


async def sign_in(client: httpx.AsyncClient, phone: str = PHONE, **device: Any) -> dict[str, Any]:
    sent = await send(client, phone, device=device.get("device_id", DEVICE["device_id"]))
    done = await verify(client, sent.json()["challenge_id"], **device)
    assert done.status_code == 200, done.text
    return dict(done.json())


def auth_header(pair: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {pair['access_token']}"}

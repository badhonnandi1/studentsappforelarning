"""``GET /v1/uploads/{purpose}/presign`` (05 §D, R-32)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from redis.asyncio import Redis

from app.core.clock import FrozenClock, get_clock
from app.core.http import create_app
from app.core.settings import Settings
from app.core.storage import Storage, get_storage
from app.modules import nfr
from tests.support.tokens import access_token, bearer

pytestmark = [pytest.mark.api, pytest.mark.integration]
NOW = datetime(2026, 11, 27, 6, 0, tzinfo=UTC)
URL = "/v1/uploads/profile_photo/presign"


@pytest.fixture
async def client(app_redis: Redis) -> AsyncIterator[httpx.AsyncClient]:
    del app_redis
    app = create_app("api", routers=nfr.routers(), settings=Settings(_env_file=None))
    store = Storage(Settings(_env_file=None, s3_bucket_uploads="sp-test-uploads"))
    app.dependency_overrides[get_storage] = lambda: store
    app.dependency_overrides[get_clock] = lambda: FrozenClock(NOW)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_presign_profile_photo(client: httpx.AsyncClient) -> None:
    user_id = uuid.uuid4()
    params: dict[str, str | int] = {"content_type": "image/png", "bytes": 1000}
    response = await client.get(URL, params=params, headers=bearer(access_token(user_id, now=NOW)))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key"].startswith(f"profile_photo/2026/11/{user_id}/")
    assert body["key"].endswith(".png")
    assert body["max_bytes"] == 2 * 1024 * 1024
    assert body["fields"]["Content-Type"] == "image/png"
    assert body["expires_at"].startswith("2026-11-27T06:10:00")


@pytest.mark.parametrize(
    ("url", "params"),
    [
        (URL, {"content_type": "image/gif", "bytes": 1000}),
        (URL, {"content_type": "image/png", "bytes": 3 * 1024 * 1024}),
        (URL, {"content_type": "image/png", "bytes": 0}),
        ("/v1/uploads/photo_solve/presign", {"content_type": "image/png", "bytes": 1}),
        ("/v1/uploads/nope/presign", {"content_type": "image/png", "bytes": 1}),
    ],
)
async def test_presign_refusals(
    client: httpx.AsyncClient, url: str, params: dict[str, str | int]
) -> None:
    response = await client.get(
        url, params=params, headers=bearer(access_token(uuid.uuid4(), now=NOW))
    )
    assert response.status_code == 422


async def test_presign_needs_a_user(client: httpx.AsyncClient) -> None:
    params: dict[str, str | int] = {"content_type": "image/png", "bytes": 10}
    assert (await client.get(URL, params=params)).status_code == 401

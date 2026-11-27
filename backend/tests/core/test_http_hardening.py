"""Hardening (05 §C.1 step 13): CORS allow-list, no-store, streamed body limit."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from app.core.http import create_app
from app.core.settings import Settings
from tests.core.test_http_app import JSON, build_router

pytestmark = pytest.mark.unit
ORIGIN = "https://app.example.com"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(_env_file=None, app_env="test", cors_origins=[ORIGIN])
    app = create_app("api", routers=[build_router()], settings=settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def preflight(client: httpx.AsyncClient, origin: str, headers: str) -> httpx.Response:
    return await client.options("/echo", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": headers,
    })  # fmt: skip


async def test_cors_allows_listed_origins_and_headers_only(client: httpx.AsyncClient) -> None:
    ok = await preflight(client, ORIGIN, "authorization,idempotency-key,x-device-id")
    assert ok.status_code == 200
    assert ok.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert ok.headers["Access-Control-Max-Age"] == "600"
    assert "Access-Control-Allow-Credentials" not in ok.headers  # bearer tokens, no cookies
    assert (await preflight(client, "https://evil.example.com", "authorization")).status_code == 400
    assert (await preflight(client, ORIGIN, "x-forged")).status_code == 400
    simple = await client.get("/livez", headers={"Origin": ORIGIN})
    assert "X-Request-ID" in simple.headers["Access-Control-Expose-Headers"]
    other = await client.get("/livez", headers={"Origin": "https://evil.example.com"})
    assert "Access-Control-Allow-Origin" not in other.headers


async def test_api_responses_are_not_cacheable(client: httpx.AsyncClient) -> None:
    assert (await client.get("/livez")).headers["Cache-Control"] == "no-store"
    assert "Cache-Control" not in (await client.get("/docs")).headers  # docs keep their own


async def test_streamed_body_without_length_is_limited(client: httpx.AsyncClient) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b'{"answer_id": 1, "p": "'
        for _ in range(300):
            yield b"x" * 1024
        yield b'"}'

    response = await client.post("/echo", content=chunks(), headers=JSON)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"

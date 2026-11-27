"""``Idempotency-Key``: replay, reuse with another body, in-flight lock, large responses."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

import httpx
import pytest
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.http import create_app
from app.core.settings import Settings
from app.modules.nfr import Idem, idempotent
from app.modules.nfr.internal.services.idempotency import request_hash

pytestmark = [pytest.mark.api, pytest.mark.db]
USER = uuid.UUID("00000000-0000-7000-8000-000000000001")
created: list[str] = []


class ThingIn(BaseModel):
    name: str
    big: bool = False


def current_user() -> uuid.UUID:
    return USER


async def reread(_session: AsyncSession, resource_id: uuid.UUID) -> dict[str, Any]:
    return {"id": str(resource_id), "reread": True}


def build_router() -> APIRouter:
    router = APIRouter()
    guard = idempotent("things.create", user=current_user, reread=reread)
    optional = idempotent("things.optional", user=current_user, required=False)

    @router.post("/things", status_code=201)
    async def create(body: ThingIn, idem: Annotated[Idem, Depends(guard)]) -> Any:
        if idem.replay is not None:
            return idem.replay
        created.append(body.name)
        thing_id = uuid.uuid4()
        out = {"id": str(thing_id), "name": body.name, "pad": "x" * (70_000 if body.big else 0)}
        return await idem.respond(201, out, resource_id=thing_id)

    @router.post("/optional")
    async def maybe(idem: Annotated[Idem, Depends(optional)]) -> Any:
        async with idem.session.begin():
            return await idem.respond(200, {"ok": True})

    return router


@pytest.fixture
async def client(session: AsyncSession, app_redis: Redis) -> AsyncIterator[httpx.AsyncClient]:
    created.clear()
    app = create_app("api", routers=[build_router()], settings=Settings(_env_file=None))

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def key() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid.uuid4())}


async def test_replay_returns_the_stored_response(client: httpx.AsyncClient) -> None:
    headers = key()
    first = await client.post("/things", json={"name": "a"}, headers=headers)
    again = await client.post("/things", json={"name": "a"}, headers=headers)
    assert first.status_code == again.status_code == 201
    assert again.json() == first.json()
    assert again.headers["Idempotent-Replay"] == "true"
    assert "Idempotent-Replay" not in first.headers
    assert created == ["a"]


async def test_same_key_other_body_is_rejected(client: httpx.AsyncClient) -> None:
    headers = key()
    await client.post("/things", json={"name": "a"}, headers=headers)
    response = await client.post("/things", json={"name": "b"}, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency_key_reused"


async def test_key_required_and_must_be_uuid(client: httpx.AsyncClient) -> None:
    missing = await client.post("/things", json={"name": "a"})
    assert missing.status_code == 422
    bad = await client.post("/things", json={"name": "a"}, headers={"Idempotency-Key": "nope"})
    assert bad.status_code == 422
    assert (await client.post("/optional")).json() == {"ok": True}
    assert (await client.post("/optional", headers=key())).status_code == 200


async def test_in_flight_request_conflicts(client: httpx.AsyncClient, app_redis: Redis) -> None:
    headers = key()
    await app_redis.set(f"idem:lock:{USER}:{headers['Idempotency-Key']}", "1")
    response = await client.post("/things", json={"name": "a"}, headers=headers)
    assert response.status_code == 409
    assert created == []


async def test_large_response_replays_by_resource_id(client: httpx.AsyncClient) -> None:
    headers = key()
    first = await client.post("/things", json={"name": "a", "big": True}, headers=headers)
    again = await client.post("/things", json={"name": "a", "big": True}, headers=headers)
    assert again.json() == {"id": first.json()["id"], "reread": True}


async def test_lock_fails_open_without_redis(client: httpx.AsyncClient) -> None:
    from app.core.redis import use_client

    use_client(Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2))
    response = await client.post("/things", json={"name": "a"}, headers=key())
    assert response.status_code == 201


def test_request_hash_is_canonical() -> None:
    assert request_hash("POST", "r", b'{"a":1,"b":2}') == request_hash(
        "POST", "r", b'{"b": 2, "a": 1}'
    )
    assert request_hash("POST", "r", b"{}") != request_hash("POST", "other", b"{}")
    assert request_hash("POST", "r", b"\xff not json")

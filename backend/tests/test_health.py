import importlib
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import ConflictError
from app.core.http import create_app

pytestmark = pytest.mark.anyio

# deployable module, service name, dependencies /readyz must check
HTTP_APPS = [
    ("app.entrypoints.api", "api", ("db", "redis")),
    ("app.entrypoints.ai_gateway", "ai-gateway", ("db", "redis")),
    ("app.entrypoints.exam_ingest", "exam-ingest", ("redis",)),
]


def client_for(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.parametrize(("module", "service"), [(m, s) for m, s, _ in HTTP_APPS])
async def test_livez(module: str, service: str) -> None:
    async with client_for(importlib.import_module(module).app) as http:
        response = await http.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": service}


@pytest.mark.parametrize(("module", "service", "deps"), HTTP_APPS)
async def test_readyz_is_503_naming_each_unreachable_dependency(
    module: str, service: str, deps: tuple[str, ...]
) -> None:
    app = importlib.import_module(module).app
    assert app.state.ready_checks == deps
    async with client_for(app) as http:
        response = await http.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "service": service} | dict.fromkeys(
        deps, "error"
    )


async def _ok() -> None:
    return None


async def test_readyz_is_200_when_every_dependency_answers() -> None:
    async with client_for(create_app("svc", {"db": _ok, "redis": _ok})) as http:
        response = await http.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "svc", "db": "ok", "redis": "ok"}


@pytest.fixture
async def http() -> AsyncIterator[AsyncClient]:
    app = create_app("svc")

    @app.get("/conflict")
    async def conflict() -> None:
        raise ConflictError("answer_id already used by another user")

    async with client_for(app) as client:
        yield client


async def test_request_id_is_echoed(http: AsyncClient) -> None:
    response = await http.get("/livez", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


async def test_unsafe_request_id_is_replaced(http: AsyncClient) -> None:
    response = await http.get("/livez", headers={"X-Request-ID": "bad id\nwith newline"})
    assert len(response.headers["X-Request-ID"]) == 32


async def test_app_errors_become_json(http: AsyncClient) -> None:
    response = await http.get("/conflict")
    assert response.status_code == 409
    assert response.json() == {
        "error": {"code": "conflict", "message": "answer_id already used by another user"}
    }

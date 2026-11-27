"""create_app: health, errors envelope, security headers, body limits (05 §E)."""

from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import APIRouter
from pydantic import BaseModel

from app.core import errors
from app.core.http import create_app
from app.core.settings import Settings

pytestmark = pytest.mark.api
JSON = {"content-type": "application/json"}

ERRORS = [
    (errors.AppError, 400, "bad_request"),
    (errors.UnauthorizedError, 401, "unauthorized"),
    (errors.ForbiddenError, 403, "forbidden"),
    (errors.NotFoundError, 404, "not_found"),
    (errors.ConflictError, 409, "conflict"),
    (errors.GoneError, 410, "expired"),
    (errors.PayloadTooLargeError, 413, "payload_too_large"),
    (errors.ValidationAppError, 422, "validation_error"),
    (errors.LockedError, 423, "locked_exam"),
    (errors.UpgradeRequiredError, 426, "upgrade_required"),
    (errors.UnavailableError, 503, "unavailable"),
]


class Body(BaseModel):
    answer_id: int


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/raise/{index}")
    async def raise_error(index: int) -> None:
        cls = ERRORS[index][0]
        raise cls("nope", details={"why": "test"})

    @router.get("/limited")
    async def limited() -> None:
        raise errors.TooManyRequestsError("slow down", retry_after=7)

    @router.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret internals")

    @router.post("/echo")
    async def echo(body: Body) -> dict[str, int]:
        return {"answer_id": body.answer_id}

    @router.post("/v1/events:batch")
    async def batch(payload: dict[str, str]) -> dict[str, int]:
        return {"size": len(payload["blob"])}

    return router


async def ok() -> None:
    return None


async def down() -> None:
    raise ConnectionError("db down")


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(_env_file=None, app_env="test")
    app = create_app(
        "api", routers=[build_router()], ready_checks={"db": ok, "redis": ok}, settings=settings
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_livez(client: httpx.AsyncClient) -> None:
    response = await client.get("/livez")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("checks", "failing"),
    [({"db": down, "redis": ok}, ["db"]), ({"db": ok, "redis": down}, ["redis"])],
)
async def test_readyz_names_failing_dependency(
    checks: dict[str, object], failing: list[str]
) -> None:
    settings = Settings(_env_file=None, app_env="test")
    app = create_app("api", ready_checks=checks, settings=settings)  # type: ignore[arg-type]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        response = await c.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "fail", "failing": failing}


async def test_readyz_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"db": "ok", "redis": "ok"}}


@pytest.mark.parametrize("index", range(len(ERRORS)))
async def test_app_errors_map_to_envelope(client: httpx.AsyncClient, index: int) -> None:
    _, status, code = ERRORS[index]
    response = await client.get(f"/raise/{index}", headers={"X-Request-ID": "req-1"})
    assert response.status_code == status
    assert response.json() == {
        "error": {
            "code": code,
            "message": "nope",
            "details": {"why": "test"},
            "request_id": "req-1",
        }
    }
    if status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_too_many_requests_sets_retry_after(client: httpx.AsyncClient) -> None:
    response = await client.get("/limited")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "7"


async def test_validation_error_shape(client: httpx.AsyncClient) -> None:
    response = await client.post("/echo", json={"answer_id": "x"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"]["fields"][0]["loc"] == ["body", "answer_id"]


async def test_unhandled_error_hides_details(client: httpx.AsyncClient) -> None:
    response = await client.get("/boom")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert "secret" not in response.text
    assert error["request_id"] == response.headers["X-Request-ID"]


async def test_unknown_route_uses_envelope(client: httpx.AsyncClient) -> None:
    response = await client.get("/nowhere")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_security_and_version_headers(client: httpx.AsyncClient) -> None:
    response = await client.get("/livez")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert response.headers["X-Min-App-Version"] == "1.0.0"
    assert "Strict-Transport-Security" in response.headers
    assert response.headers["Cache-Control"] == "no-store"


async def test_body_limit_default(client: httpx.AsyncClient) -> None:
    pad = "x" * (256 * 1024 - 40)
    ok_body = '{"answer_id": 1, "p": "' + pad + '"}'
    assert len(ok_body) <= 256 * 1024
    assert (await client.post("/echo", content=ok_body, headers=JSON)).status_code == 200
    big = '{"answer_id": 1, "p": "' + "x" * (257 * 1024) + '"}'
    response = await client.post("/echo", content=big, headers=JSON)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_batch_endpoint_accepts_one_megabyte(client: httpx.AsyncClient) -> None:
    body = '{"blob": "' + "x" * (1024 * 1024 - 20) + '"}'
    response = await client.post("/v1/events:batch", content=body, headers=JSON)
    assert response.status_code == 200
    too_big = '{"blob": "' + "x" * (1024 * 1024 + 10) + '"}'
    assert (await client.post("/v1/events:batch", content=too_big, headers=JSON)).status_code == 413


async def test_docs_hidden_in_prod_like_env() -> None:
    settings = Settings(_env_file=None, app_env="test")
    assert create_app("api", settings=settings).docs_url == "/docs"

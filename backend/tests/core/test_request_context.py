import httpx
import pytest
import structlog
from fastapi import FastAPI

from app.core.request_context import RequestContextMiddleware, current_request_id

pytestmark = pytest.mark.unit


def build() -> FastAPI:
    app = FastAPI()

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str | None]:
        return {
            "rid": current_request_id(),
            "trace": structlog.contextvars.get_contextvars().get("trace_id"),
        }

    app.add_middleware(RequestContextMiddleware)
    return app


async def get(path: str, headers: dict[str, str] | None = None) -> httpx.Response:
    transport = httpx.ASGITransport(app=build())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get(path, headers=headers)


async def test_valid_request_id_echoed() -> None:
    response = await get("/items/1", {"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"
    assert response.json()["rid"] == "abc-123"


async def test_invalid_request_id_replaced() -> None:
    response = await get("/items/1", {"X-Request-ID": "bad id with spaces <script>"})
    rid = response.headers["X-Request-ID"]
    assert rid != "bad id with spaces <script>"
    assert len(rid) == 32


async def test_traceparent_bound() -> None:
    trace = "4bf92f3577b34da6a3ce929d0e0e4736"
    response = await get("/items/1", {"traceparent": f"00-{trace}-00f067aa0ba902b7-01"})
    assert response.json()["trace"] == trace


async def test_access_log_has_route_template_not_raw_path() -> None:
    with structlog.testing.capture_logs() as logs:
        await get("/items/01712345678?phone=01712345678")
    line = next(entry for entry in logs if entry["event"] == "request")
    assert line["route"] == "/items/{item_id}"
    assert "01712345678" not in repr(line)
    assert line["status"] == 200


async def test_websocket_scope_passes_through() -> None:
    seen: list[str] = []

    async def inner(scope: dict[str, object], receive: object, send: object) -> None:
        seen.append(str(scope["type"]))

    await RequestContextMiddleware(inner)({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    assert seen == ["lifespan"]

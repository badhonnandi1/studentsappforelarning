"""The HTTP deployables boot through their lifespans and report ready."""

from __future__ import annotations

import importlib

import httpx
import pytest

from app.core.redis import get_redis
from app.core.security import actor as actor_mod

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("in_process_env")]


@pytest.mark.parametrize(
    ("module", "service", "checks"),
    [
        ("app.entrypoints.api.main", "api", {"db", "redis"}),
        ("app.entrypoints.ai_gateway.main", "ai-gateway", {"db", "redis"}),
        ("app.entrypoints.exam_ingest.main", "exam-ingest", {"redis"}),
    ],
)
async def test_boots_live_and_ready(module: str, service: str, checks: set[str]) -> None:
    app = importlib.import_module(module).app
    assert app.state.service == service
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/livez")).json() == {"status": "ok"}
            ready = await client.get("/readyz")
            assert ready.status_code == 200, ready.text
            assert set(ready.json()["checks"]) == checks
        assert (actor_mod._loader is not None) == ("db" in checks)  # AUTH startup hook ran
    with pytest.raises(RuntimeError):
        get_redis()  # closed on shutdown


async def test_api_mounts_module_routes() -> None:
    app = importlib.import_module("app.entrypoints.api.main").app
    paths = set(app.openapi()["paths"])  # FastAPI 0.165 nests included routers in app.routes
    assert {"/v1/config/client", "/v1/admin/audit-log"} <= paths

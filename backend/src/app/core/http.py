"""``create_app``: the one way every HTTP deployable is built (05 §C.10 middleware order).

This module must not import ``app.core.db``: exam-ingest uses it without Postgres. Readiness
checks are passed in by each entry point.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.core.errors import add_error_handlers
from app.core.middleware import BodyLimitMiddleware, SecurityHeadersMiddleware
from app.core.request_context import RequestContextMiddleware
from app.core.settings import Settings, get_settings

ReadyCheck = Callable[[], Awaitable[object]]
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]
READY_TIMEOUT_S = 2.0
# Request headers browsers may send cross-origin: exactly the ones the API reads.
CORS_REQUEST_HEADERS = (
    "Authorization",
    "Content-Type",
    "Idempotency-Key",
    "X-Device-Id",
    "X-Step-Up-Token",
    "X-Request-ID",
    "traceparent",
)
CORS_EXPOSED_HEADERS = ("X-Request-ID", "Retry-After", "Idempotent-Replay", "X-Min-App-Version")
CORS_MAX_AGE_S = 600


async def run_ready_checks(checks: Mapping[str, ReadyCheck]) -> list[str]:
    """Run every check concurrently with a 2 s budget; return the names that failed."""

    async def one(check: ReadyCheck) -> bool:
        try:
            await asyncio.wait_for(check(), READY_TIMEOUT_S)
        except Exception:
            return False
        return True

    names = list(checks)
    results = await asyncio.gather(*(one(checks[name]) for name in names))
    return [name for name, ok in zip(names, results, strict=True) if not ok]


def health_router(checks: Mapping[str, ReadyCheck]) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/livez")
    async def livez() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/readyz")
    async def readyz() -> JSONResponse:
        failing = await run_ready_checks(checks)
        if failing:
            return JSONResponse({"status": "fail", "failing": failing}, status_code=503)
        return JSONResponse({"status": "ok", "checks": dict.fromkeys(checks, "ok")})

    return router


@asynccontextmanager
async def _no_lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield


def create_app(
    service: str,
    *,
    routers: Sequence[APIRouter] = (),
    ready_checks: Mapping[str, ReadyCheck] | None = None,
    lifespan: Lifespan | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    docs = not settings.is_deployed
    app = FastAPI(
        title=f"studyplatform-{service}",
        version="1",
        lifespan=lifespan or _no_lifespan,
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.state.service = service
    app.state.min_app_version = settings.min_app_version
    add_error_handlers(app)
    app.include_router(health_router(ready_checks or {}))
    for router in routers:
        app.include_router(router)

    # Starlette wraps in reverse order of add_middleware: the last added is outermost.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=list(CORS_REQUEST_HEADERS),
        expose_headers=list(CORS_EXPOSED_HEADERS),
        max_age=CORS_MAX_AGE_S,
    )
    app.add_middleware(SecurityHeadersMiddleware, min_app_version=lambda: app.state.min_app_version)
    app.add_middleware(RequestContextMiddleware)
    return app

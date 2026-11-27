"""FastAPI app factory shared by the HTTP entry points (api, ai-gateway, exam-ingest).

Every app gets the fastapi-starter wiring (structlog request logging with
X-Request-ID, AppError handlers) and two ops routes:

- ``GET /livez``: the process is up. No dependency calls.
- ``GET /readyz``: each dependency this deployable needs answers within
  READY_TIMEOUT_S. 503 names the one that did not. The checks are passed in by
  the entry point, so this file never imports the database (exam-ingest uses it).
"""

import asyncio
from collections.abc import Awaitable, Callable, Mapping

import structlog
from fastapi import FastAPI, Response, status

from app.core.errors import add_error_handlers
from app.core.logging import RequestLogMiddleware, configure_logging
from app.core.settings import get_settings

ReadyCheck = Callable[[], Awaitable[object]]
READY_TIMEOUT_S = 2.0

log = structlog.get_logger(__name__)


def create_app(service: str, ready_checks: Mapping[str, ReadyCheck] | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(json=settings.log_json, level=settings.log_level)
    docs = settings.app_env not in ("staging", "prod")
    app = FastAPI(
        title=f"studyplatform {service}",
        version="0.1.0",
        docs_url="/docs" if docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(RequestLogMiddleware)
    add_error_handlers(app)
    checks = dict(ready_checks or {})
    app.state.ready_checks = tuple(checks)

    @app.get("/livez", tags=["ops"])
    async def livez() -> dict[str, str]:
        return {"status": "ok", "service": service}

    @app.get("/readyz", tags=["ops"])
    async def readyz(response: Response) -> dict[str, str]:
        result = {"status": "ok", "service": service}
        for name, check in checks.items():
            try:
                await asyncio.wait_for(check(), READY_TIMEOUT_S)
                result[name] = "ok"
            except Exception as exc:  # any failure means not ready
                log.warning("readiness check failed", dependency=name, error=str(exc))
                result[name] = "error"
                result["status"] = "unavailable"
        if result["status"] != "ok":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return result

    return app

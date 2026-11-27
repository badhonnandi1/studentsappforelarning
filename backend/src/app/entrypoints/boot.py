"""Process start-up shared by every deployable.

This module must not import ``app.core.db``: exam-ingest uses it and never touches Postgres.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.http import Lifespan
from app.core.logging import configure_logging
from app.core.redis import close_redis, init_redis
from app.core.security.jwt import init_token_keys
from app.core.settings import Settings, get_settings
from app.core.telemetry import configure_telemetry


def configure_process(settings: Settings, service: str) -> None:
    configure_logging(json=settings.log_json, level=settings.log_level)
    configure_telemetry(settings, service)
    init_token_keys(settings)
    init_redis(settings.redis_url)


def light_lifespan(service: str) -> Lifespan:
    """Logging, telemetry, token keys and Redis; no database."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_process(get_settings(), service)
        try:
            yield
        finally:
            await close_redis()

    return lifespan


def install_stop_signals(stop: asyncio.Event) -> None:
    """SIGTERM and SIGINT set ``stop``, so the current batch finishes before exit."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

"""Start-up for the deployables that use Postgres: api, ai-gateway and workers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import Role, dispose_engine, init_engine, ping_db
from app.core.http import Lifespan, ReadyCheck
from app.core.redis import close_redis, ping_redis
from app.core.security.crypto import init_crypto
from app.core.settings import Settings, get_settings
from app.entrypoints.boot import configure_process
from app.modules.registry import load_models

READY_CHECKS: dict[str, ReadyCheck] = {"db": ping_db, "redis": ping_redis}


async def start_stack(settings: Settings, service: str, role: Role) -> None:
    configure_process(settings, service)
    load_models()  # complete metadata: cross-module FKs (e.g. platform -> identity.users)
    init_engine(settings, role)
    await init_crypto(settings)


async def stop_stack() -> None:
    await dispose_engine()
    await close_redis()


def db_lifespan(service: str) -> Lifespan:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await start_stack(get_settings(), service, "api")
        try:
            yield
        finally:
            await stop_stack()

    return lifespan

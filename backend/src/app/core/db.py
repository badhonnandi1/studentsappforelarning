"""Async engine and sessions (asyncpg).

Services own transactions (``async with session.begin()``); ``get_session`` only hands out a
session. With ``DB_POOL_MODE=pgbouncer`` prepared-statement caches are disabled, which
PgBouncer transaction pooling requires.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import Settings

Role = Literal["api", "worker"]
WORKER_STATEMENT_TIMEOUT_MS = 30_000

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def engine_options(settings: Settings, role: Role = "api") -> dict[str, Any]:
    statement_ms = (
        settings.db_statement_timeout_ms if role == "api" else WORKER_STATEMENT_TIMEOUT_MS
    )
    connect_args: dict[str, Any] = {
        "server_settings": {
            "statement_timeout": str(statement_ms),
            "lock_timeout": str(settings.db_lock_timeout_ms),
            "idle_in_transaction_session_timeout": str(settings.db_idle_in_transaction_timeout_ms),
            "application_name": f"studyplatform-{role}",
            "timezone": "UTC",
        }
    }
    if settings.db_pool_mode == "pgbouncer":
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4().hex}__"
    return {
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "connect_args": connect_args,
    }


def make_engine(url: str, settings: Settings, role: Role = "api") -> AsyncEngine:
    return create_async_engine(url, **engine_options(settings, role))


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


def init_engine(settings: Settings, role: Role = "api") -> AsyncEngine:
    global _engine, _sessionmaker
    _engine = make_engine(settings.database_url, settings, role)
    _sessionmaker = make_sessionmaker(_engine)
    return _engine


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


def sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("database engine not initialised; call init_engine() at startup")
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Tests override it with a session in a rolled-back transaction."""
    async with sessionmaker()() as session:
        yield session


async def ping_db() -> None:
    async with sessionmaker()() as session:
        await session.execute(text("SELECT 1"))

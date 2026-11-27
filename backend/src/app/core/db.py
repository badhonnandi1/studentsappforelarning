"""PostgreSQL 17 connection setup (SQLAlchemy 2 + psycopg 3).

Creating the engine does not open a connection; the first query does. Each module
keeps its tables in its own schema (see app.modules.registry). exam-ingest must
never import this file (enforced by import-linter, see .importlinter).
"""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.settings import get_settings


@lru_cache
def get_engine() -> Engine:
    """Sync engine, used by Alembic and the Postgres job runner."""
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_async_engine() -> AsyncEngine:
    """Async engine for request handlers. psycopg 3 serves both sync and async."""
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_async_engine(), expire_on_commit=False)


async def ping_db() -> None:
    """Readiness check: one round trip to PostgreSQL."""
    async with get_async_engine().connect() as connection:
        await connection.execute(text("SELECT 1"))

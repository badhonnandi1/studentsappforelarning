"""Shared fixtures. The environment is set before anything imports ``app``."""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("TEST_PHONE_OTP", "123456")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "localdev")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "localdev-secret")
os.environ.setdefault("S3_ENDPOINT_URL", "http://127.0.0.1:59000")
from tests.support.keys import SECRET_VARS, install_test_keys

install_test_keys(os.environ)

from collections.abc import AsyncIterator, Callable

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from app.core.redis import use_client
from tests.support import db as test_db


def worker_id() -> str:
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


@pytest.fixture(scope="session")
async def migrated() -> str:
    """Migrator URL of this worker's freshly cloned, fully migrated database."""
    return await test_db.clone_for_worker(worker_id())


@pytest.fixture(scope="session")
async def engine(migrated: str) -> AsyncIterator[AsyncEngine]:
    """Engine connected as ``app_rw``, the role the services use in production."""
    eng = create_async_engine(test_db.app_url(migrated), pool_size=5, max_overflow=5)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """A session inside an outer transaction that is always rolled back.

    Service code calling ``session.begin()`` gets a SAVEPOINT, so commits inside services
    are real to the code under test and invisible to every other test.
    """
    async with engine.connect() as connection:
        outer = await connection.begin()
        db_session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            await outer.rollback()


@pytest.fixture
def sessions(session: AsyncSession) -> Callable[[], AsyncSession]:
    """New sessions on the same rolled-back connection; each ``begin()`` is a SAVEPOINT."""
    connection = session.bind
    assert isinstance(connection, AsyncConnection)

    def factory() -> AsyncSession:
        return AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )

    return factory


REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://127.0.0.1:56379")


def redis_db_index() -> int:
    """Database 0 is for local runs; each xdist worker gets its own index from 1."""
    worker = worker_id()
    return 1 + (int(worker[2:]) if worker.startswith("gw") else 0)


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(f"{REDIS_URL}/{redis_db_index()}")
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()


@pytest.fixture
async def app_redis(redis: Redis) -> AsyncIterator[Redis]:
    """The test Redis installed as the application's client."""
    use_client(redis)
    try:
        yield redis
    finally:
        use_client(None)


@pytest.fixture
def no_env_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """pydantic-settings deep-merges dict settings from the environment into constructor
    values, so tests that build Settings with specific keys must remove the global test keys."""
    for name in SECRET_VARS:
        monkeypatch.delenv(name, raising=False)

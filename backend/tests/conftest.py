"""Shared fixtures. The environment is set before anything imports ``app``."""

from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("TEST_PHONE_OTP", "123456")

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

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

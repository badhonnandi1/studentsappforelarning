"""Committed databases: one per test module, cloned from the migrated template."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tests.support import db as test_db


@pytest.fixture(scope="module")
async def committed_engine(migrated: str) -> AsyncIterator[AsyncEngine]:
    del migrated  # the template must exist first
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    name = f"sp_conc_{worker}_{uuid.uuid4().hex[:8]}"
    url = await test_db.create_from_template(name)
    engine = create_async_engine(test_db.app_url(url), pool_size=10, max_overflow=0)
    try:
        yield engine
    finally:
        await engine.dispose()
        await test_db.drop_database(name)

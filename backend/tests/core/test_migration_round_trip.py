"""``downgrade base`` then ``upgrade head`` on a copy of the template, then ``alembic check``."""

from __future__ import annotations

import asyncio
import os

import pytest
from alembic import command

from tests.support import db as test_db

pytestmark = [pytest.mark.db, pytest.mark.slow]


async def test_downgrade_to_base_and_back() -> None:
    name = f"sp_roundtrip_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"
    url = await test_db.create_from_template(name)
    try:
        cfg = test_db.alembic_config(url)
        await asyncio.to_thread(command.downgrade, cfg, "base")
        await asyncio.to_thread(command.upgrade, cfg, "head")
        await asyncio.to_thread(command.check, cfg)
    finally:
        await test_db.drop_database(name)

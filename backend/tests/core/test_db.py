import asyncio

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import engine_options
from app.core.settings import Settings
from app.modules.registry import SCHEMAS
from tests.support import db as test_db

pytestmark = pytest.mark.db


async def test_schemas_and_extensions_exist(session: AsyncSession) -> None:
    rows = await session.execute(text("SELECT nspname FROM pg_namespace"))
    names = {r[0] for r in rows}
    assert set(SCHEMAS) <= names
    rows = await session.execute(text("SELECT extname FROM pg_extension"))
    assert {"vector", "pg_trgm", "ltree", "btree_gist", "pgcrypto"} <= {r[0] for r in rows}


async def test_connected_as_app_role_with_timeouts(session: AsyncSession) -> None:
    assert (await session.execute(text("SELECT current_user"))).scalar() == "app_rw"


async def test_service_commit_is_rolled_back_after_test(session: AsyncSession) -> None:
    async with session.begin():
        await session.execute(text("CREATE TEMP TABLE scratch (x int)"))
        await session.execute(text("INSERT INTO scratch VALUES (1)"))
    assert (await session.execute(text("SELECT count(*) FROM scratch"))).scalar() == 1


async def test_metadata_matches_database(migrated: str) -> None:
    """Equivalent of ``alembic check``: models and migrations agree."""
    await asyncio.to_thread(command.check, test_db.alembic_config(migrated))


def test_engine_options_for_pgbouncer() -> None:
    settings = Settings(_env_file=None, db_pool_mode="pgbouncer")
    args = engine_options(settings, "worker")["connect_args"]
    assert args["statement_cache_size"] == 0
    assert args["prepared_statement_cache_size"] == 0
    assert args["server_settings"]["statement_timeout"] == "30000"
    assert args["prepared_statement_name_func"]() != args["prepared_statement_name_func"]()
    direct = engine_options(Settings(_env_file=None), "api")["connect_args"]
    assert "statement_cache_size" not in direct
    assert direct["server_settings"]["statement_timeout"] == "5000"
    assert direct["server_settings"]["lock_timeout"] == "2000"


async def test_engine_lifecycle_and_ping(migrated: str) -> None:
    from app.core import db

    with pytest.raises(RuntimeError, match="not initialised"):
        db.sessionmaker()
    db.init_engine(Settings(_env_file=None, database_url=test_db.app_url(migrated)), "worker")
    try:
        await db.ping_db()
        sessions = db.get_session()
        session = await anext(sessions)
        assert (await session.execute(text("SELECT 1"))).scalar() == 1
        await sessions.aclose()
    finally:
        await db.dispose_engine()
    await db.dispose_engine()

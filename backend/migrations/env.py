"""Alembic environment: async engine, every module schema, partitions ignored by autogenerate.

The URL is ``sqlalchemy.url`` when a caller sets it (tests), else ``DATABASE_MIGRATOR_URL``.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # revisions import migrations.helpers

from app.core.db_base import Base
from app.core.settings import get_settings
from app.modules.registry import SCHEMAS, load_models

load_models()
config = context.config
target_metadata = Base.metadata
PARTITION_NAME = re.compile(r"_p\d{6,8}$")


def database_url() -> str:
    return (
        config.get_main_option("sqlalchemy.url")
        or os.environ.get("DATABASE_MIGRATOR_URL")
        or get_settings().database_migrator_url
    )


def include_name(name: str | None, type_: str, _parent: object) -> bool:
    if type_ == "schema":
        return name in SCHEMAS
    if type_ == "table" and name is not None:
        return PARTITION_NAME.search(name) is None
    return True


def run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(database_url(), poolclass=pool.NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())

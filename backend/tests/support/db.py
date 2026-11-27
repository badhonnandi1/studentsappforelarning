"""Test databases: one migrated template per migration fingerprint, cloned per xdist worker.

The template is built once (under an advisory lock, so parallel workers wait for one build)
and every worker gets ``CREATE DATABASE … TEMPLATE``, which takes well under a second.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config

BACKEND = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://app_migrator:app_migrator@127.0.0.1:55432/studyplatform_test",
)
APP_USER, APP_PASSWORD = "app_rw", "app_rw"
LOCK_ID = 7_212_026


def fingerprint() -> str:
    digest = hashlib.sha256()
    sources = [
        *sorted((BACKEND / "migrations").rglob("*.py")),
        *sorted((BACKEND / "src/app/core/jobs").rglob("*.py")),
    ]
    for path in sources:
        digest.update(path.read_bytes())
    # Migrations create partitions relative to today, so a template is rebuilt each UTC day.
    digest.update(datetime.now(UTC).date().isoformat().encode())
    return digest.hexdigest()[:10]


def with_database(
    url: str, name: str, *, user: str | None = None, password: str | None = None
) -> str:
    scheme, rest = url.split("://", 1)
    creds, host_db = rest.split("@", 1)
    host = host_db.rsplit("/", 1)[0]
    if user is not None:
        creds = f"{user}:{password}"
    return f"{scheme}://{creds}@{host}/{name}"


def raw_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


async def upgrade(url: str, revision: str = "head") -> None:
    await asyncio.to_thread(command.upgrade, alembic_config(url), revision)


async def clone_for_worker(worker: str) -> str:
    """Return the migrator URL of a fresh database for this worker."""
    template = f"sp_tpl_{fingerprint()}"
    target = f"sp_test_{worker}"
    admin = await asyncpg.connect(raw_dsn(with_database(ADMIN_URL, "postgres")))
    try:
        await admin.execute("SELECT pg_advisory_lock($1)", LOCK_ID)
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", template)
        if not exists:
            stale = await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'sp_tpl_%'"
            )
            for row in stale:
                await admin.execute(f'DROP DATABASE IF EXISTS "{row["datname"]}" WITH (FORCE)')
            await admin.execute(f'CREATE DATABASE "{template}"')
            try:
                await upgrade(with_database(ADMIN_URL, template))
            except BaseException:
                await admin.execute(f'DROP DATABASE IF EXISTS "{template}" WITH (FORCE)')
                raise
        await admin.execute(f'DROP DATABASE IF EXISTS "{target}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{target}" TEMPLATE "{template}"')
    finally:
        await admin.execute("SELECT pg_advisory_unlock($1)", LOCK_ID)
        await admin.close()
    return with_database(ADMIN_URL, target)


async def create_from_template(name: str) -> str:
    """A committed database for concurrency tests; caller drops it with ``drop_database``."""
    template = f"sp_tpl_{fingerprint()}"
    admin = await asyncpg.connect(raw_dsn(with_database(ADMIN_URL, "postgres")))
    try:
        await admin.execute("SELECT pg_advisory_lock($1)", LOCK_ID)
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    finally:
        await admin.execute("SELECT pg_advisory_unlock($1)", LOCK_ID)
        await admin.close()
    return with_database(ADMIN_URL, name)


async def drop_database(name: str) -> None:
    admin = await asyncpg.connect(raw_dsn(with_database(ADMIN_URL, "postgres")))
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
    finally:
        await admin.close()


def app_url(migrator_url: str) -> str:
    name = migrator_url.rsplit("/", 1)[1]
    return with_database(migrator_url, name, user=APP_USER, password=APP_PASSWORD)

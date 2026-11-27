"""Environment pointing the deployables at this worker's test database and Redis."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.core.settings import get_settings
from tests.conftest import REDIS_URL, redis_db_index
from tests.support import db as test_db


@pytest.fixture
def deploy_env(migrated: str) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": test_db.app_url(migrated),
        "REDIS_URL": f"{REDIS_URL}/{redis_db_index()}",
    }


@pytest.fixture
def in_process_env(deploy_env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in ("DATABASE_URL", "REDIS_URL"):
        monkeypatch.setenv(name, deploy_env[name])
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

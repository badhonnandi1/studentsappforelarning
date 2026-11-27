"""NFR fixtures: session factories on the test connection, Redis installed as the app client."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from app.core import ratelimit
from app.core.clock import FrozenClock
from app.modules.nfr.internal.services import runtime_config

NOW = datetime(2026, 1, 15, 6, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


@pytest.fixture(autouse=True)
def fresh_runtime_config() -> Iterator[None]:
    runtime_config._cache = None
    yield
    runtime_config._cache = None
    ratelimit.set_tier_overrides({})

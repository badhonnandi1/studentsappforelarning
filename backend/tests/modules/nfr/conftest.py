"""NFR fixtures: session factories on the test connection, Redis installed as the app client."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.core import ratelimit
from app.core.clock import FrozenClock
from app.modules.nfr.internal.services import runtime_config

NOW = datetime(2026, 1, 15, 6, 0, tzinfo=UTC)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(NOW)


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


@pytest.fixture(autouse=True)
def fresh_runtime_config() -> Iterator[None]:
    runtime_config._cache = None
    yield
    runtime_config._cache = None
    ratelimit.set_tier_overrides({})

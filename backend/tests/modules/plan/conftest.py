"""PLAN fixtures: field encryption, a fake gateway and a clock in the current month."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from app.core.clock import FrozenClock
from app.core.security import crypto
from app.core.settings import Settings
from app.modules.plan.internal import providers
from app.modules.plan.internal.providers.sms_fake import FakeSmsGateway
from app.modules.plan.internal.services import templates


@pytest.fixture(autouse=True)
async def field_crypto() -> None:
    await crypto.init_crypto(Settings(_env_file=None))


@pytest.fixture
def fake_sms() -> Iterator[FakeSmsGateway]:
    fake = FakeSmsGateway(Settings(_env_file=None))
    providers.use_gateway(fake)
    templates.clear_cache()
    yield fake
    providers.use_gateway(None)
    templates.clear_cache()


@pytest.fixture
def now_clock() -> FrozenClock:
    """SMS partitions exist from the current month onward."""
    return FrozenClock(datetime.now(UTC))

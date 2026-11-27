from datetime import UTC, datetime, timedelta

import pytest

from app.core.clock import FrozenClock, SystemClock, get_clock
from app.core.ids import uuid7, uuid7_time_ms

pytestmark = pytest.mark.unit


def test_frozen_clock_moves_only_when_told() -> None:
    clock = FrozenClock(datetime(2026, 3, 1, tzinfo=UTC))
    assert clock.now() == datetime(2026, 3, 1, tzinfo=UTC)
    clock.advance(minutes=5)
    assert clock.now() == datetime(2026, 3, 1, 0, 5, tzinfo=UTC)
    clock.advance(timedelta(hours=1))
    assert clock.now().hour == 1
    clock.set(datetime(2027, 1, 1, tzinfo=UTC))
    assert clock.now().year == 2027


def test_frozen_clock_refuses_naive() -> None:
    with pytest.raises(ValueError, match="aware"):
        FrozenClock(datetime(2026, 1, 1))


def test_system_clock_is_aware() -> None:
    assert SystemClock().now().tzinfo is UTC
    assert isinstance(get_clock(), SystemClock)


def test_uuid7_version_variant_and_order() -> None:
    ids = [uuid7() for _ in range(5000)]
    assert all(i.version == 7 for i in ids)
    assert all(i.variant == "specified in RFC 4122" for i in ids)
    assert ids == sorted(ids)
    assert len(set(ids)) == len(ids)


def test_uuid7_embeds_time() -> None:
    before = int(datetime.now(UTC).timestamp() * 1000)
    value = uuid7_time_ms(uuid7())
    assert before - 5 <= value <= before + 1000

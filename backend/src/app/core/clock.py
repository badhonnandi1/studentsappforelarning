"""Injected time. Code never calls ``datetime.now()`` directly; tests use ``FrozenClock``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    """A clock that only moves when told to."""

    def __init__(self, at: datetime | None = None) -> None:
        self._now = at or datetime(2026, 1, 15, 6, 0, tzinfo=UTC)
        if self._now.tzinfo is None:
            raise ValueError("FrozenClock needs an aware datetime")

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta | None = None, **kwargs: float) -> datetime:
        self._now += delta if delta is not None else timedelta(**kwargs)
        return self._now

    def set(self, at: datetime) -> None:
        self._now = at


_system = SystemClock()


def get_clock() -> Clock:
    """FastAPI dependency and plain accessor; tests override it."""
    return _system

"""Bangladesh dates. Servers run in UTC and Dhaka is UTC+6 with no DST, so between 00:00 and
06:00 Dhaka time the UTC date is still the previous day (starter copy, extended)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

DHAKA = timezone(timedelta(hours=6), "Asia/Dhaka")
SATURDAY = 5  # date.weekday(): Monday is 0


def dhaka_date(ts: datetime) -> date:
    if ts.tzinfo is None:
        raise ValueError("dhaka_date needs an aware datetime")
    return ts.astimezone(DHAKA).date()


def dhaka_today(now: datetime | None = None) -> date:
    return dhaka_date(now or datetime.now(UTC))


def dhaka_day_range(start: date, end: date | None = None) -> tuple[datetime, datetime]:
    """Half-open ``[start, end + 1 day)`` in Dhaka time, so the last day is included in full."""
    return (
        datetime.combine(start, time(), DHAKA),
        datetime.combine(end or start, time(), DHAKA) + timedelta(days=1),
    )


def dhaka_week_start(day: date) -> date:
    """The Saturday on or before ``day``: the Bangladesh school week starts on Saturday."""
    return day - timedelta(days=(day.weekday() - SATURDAY) % 7)


def dhaka_week_key(day: date) -> str:
    """Weekly leaderboard and streak bucket, named by its Saturday: ``2026-01-10``."""
    return dhaka_week_start(day).isoformat()


def dhaka_month_key(day: date) -> str:
    return f"{day:%Y-%m}"


def age_on(birth: date, on: date) -> int:
    """Whole years; a 29 February birthday counts from 1 March in non-leap years."""
    years = on.year - birth.year
    if (on.month, on.day) < (birth.month, birth.day):
        years -= 1
    return years

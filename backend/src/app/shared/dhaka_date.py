"""Servers run in UTC and Dhaka is UTC+6 (no DST), so between 00:00 and 06:00 Dhaka a UTC date is still yesterday."""

from datetime import date, datetime, time, timedelta, timezone

DHAKA = timezone(timedelta(hours=6), "Asia/Dhaka")


def dhaka_today(now: datetime | None = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(DHAKA).date()


def dhaka_day_range(start: date, end: date | None = None) -> tuple[datetime, datetime]:
    """Half-open [start, end) so the last Dhaka day of a report is included in full."""
    return datetime.combine(start, time(), DHAKA), datetime.combine(end or start, time(), DHAKA) + timedelta(days=1)

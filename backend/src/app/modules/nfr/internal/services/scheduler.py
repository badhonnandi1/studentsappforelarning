"""Periodic jobs. Every worker may tick; ``dedupe_key`` makes each period enqueue once."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nfr.internal.services.enqueue import enqueue
from app.shared.dhaka_date import DHAKA


@dataclass(frozen=True)
class Periodic:
    kind: str
    queue: str
    slot: Callable[[datetime], tuple[str, datetime, datetime]]  # now -> (key, run_at, until)


def daily_dhaka(at: time, prefix: str) -> Callable[[datetime], tuple[str, datetime, datetime]]:
    def slot(now: datetime) -> tuple[str, datetime, datetime]:
        day = now.astimezone(DHAKA).date()
        run_at = datetime.combine(day, at, DHAKA)
        return f"{prefix}:{day.isoformat()}", run_at, run_at + timedelta(days=1)

    return slot


def hourly(prefix: str) -> Callable[[datetime], tuple[str, datetime, datetime]]:
    def slot(now: datetime) -> tuple[str, datetime, datetime]:
        start = now.replace(minute=0, second=0, microsecond=0)
        return f"{prefix}:{start:%Y%m%dT%H}", start, start + timedelta(hours=1)

    return slot


PERIODIC: list[Periodic] = [
    Periodic("platform.partition.maintain", "maintenance", daily_dhaka(time(2), "partitions")),
    Periodic("platform.retention.purge", "maintenance", hourly("retention")),
]


def periodic_kinds() -> list[str]:
    return [p.kind for p in PERIODIC]


def register_periodic(job: Periodic) -> None:
    if any(p.kind == job.kind for p in PERIODIC):
        raise ValueError(f"periodic job {job.kind} registered twice")
    PERIODIC.append(job)


async def tick(session: AsyncSession, now: datetime) -> int:
    """Enqueue the current slot of every periodic job; return how many were new."""
    created = 0
    for job in PERIODIC:
        key, run_at, until = job.slot(now)
        new = await enqueue(
            session,
            job.kind,
            {},
            now=now,
            queue=job.queue,
            run_at=run_at,
            dedupe_key=key,
            dedupe_until=until,
        )
        created += new is not None
    return created

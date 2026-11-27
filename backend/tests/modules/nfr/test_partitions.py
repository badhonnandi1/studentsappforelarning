"""Partition maintenance (create ahead, drop expired, privileges) and retention purges."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.nfr import enqueue
from app.modules.nfr.contracts.jobs import JobContext
from app.modules.nfr.internal.jobs import partition_maintenance as pm
from app.modules.nfr.internal.jobs import retention
from app.modules.nfr.internal.models import DeadJob, IdempotencyKey

pytestmark = pytest.mark.db
SPEC = pm.PartitionSpec("platform.processed_events", "day", 3, retain=14, droppable=True)


async def exists(session: AsyncSession, name: str) -> bool:
    found = await session.execute(text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name})
    return bool(found.scalar_one())


def child(day: date) -> str:
    return f"platform.processed_events_p{day:%Y%m%d}"


async def test_maintain_creates_drops_and_grants(session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    old = today - timedelta(days=40)
    report = await pm.maintain(session, old, (SPEC,))
    assert report == {"platform.processed_events": {"created": 4, "dropped": 0}}
    assert await exists(session, child(old))
    await session.execute(  # app_rw can write into a partition the function created
        text(
            "INSERT INTO platform.processed_events (consumer, event_id, event_recorded_on) "
            "VALUES ('c', :id, :d)"
        ),
        {"id": uuid.uuid4(), "d": old},
    )
    report = await pm.maintain(session, today, (SPEC,))
    assert report["platform.processed_events"]["dropped"] >= 3
    assert not await exists(session, child(old))
    assert await exists(session, child(today))


async def test_default_list_skips_missing_tables(session: AsyncSession) -> None:
    report = await pm.maintain(session, datetime.now(UTC).date())
    assert set(report) == {"platform.outbox", "platform.processed_events"}


def test_cutoffs() -> None:
    assert pm.months_before(date(2026, 1, 15), 1) == date(2025, 12, 1)
    assert pm.months_before(date(2026, 3, 31), 36) == date(2023, 3, 1)
    audit = pm.PartitionSpec("x.y", "month", 3, retain=36, droppable=False)
    assert pm.cutoff(audit, date(2026, 5, 9)) == date(2023, 5, 1)
    assert pm.cutoff(SPEC, date(2026, 5, 20)) == date(2026, 5, 6)
    assert pm.cutoff(pm.PartitionSpec("x.y", "day", 1, None, False), date(2026, 1, 1)) is None


async def test_handlers_run(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    ctx = JobContext(uuid.uuid4(), "k", "maintenance", 1, session, now)
    await pm.handle(ctx, {"date": now.date().isoformat()})
    await pm.handle(ctx, {})
    await retention.handle(ctx, {})


async def test_retention_purges_only_expired(session: AsyncSession) -> None:
    clock = FrozenClock(datetime(2026, 1, 15, tzinfo=UTC))
    now = clock.now()
    for expires in (now - timedelta(seconds=1), now + timedelta(days=1)):
        session.add(
            IdempotencyKey(
                user_id=uuid.uuid4(),
                key=uuid.uuid4(),
                request_hash=b"h",
                method="POST",
                route="r",
                expires_at=expires,
            )
        )
    session.add(
        DeadJob(
            id=uuid.uuid4(),
            original_job_id=uuid.uuid4(),
            kind="k",
            queue="default",
            payload={},
            attempts=8,
            last_error="e",
            resolved_at=now - timedelta(days=31),
        )
    )
    await enqueue(
        session,
        "k",
        {},
        now=now - timedelta(days=2),
        dedupe_key="old",
        dedupe_until=now - timedelta(days=1),
    )
    await session.execute(text("UPDATE platform.jobs SET status = 'done'"))
    await session.flush()
    report = await retention.purge(session, now)
    assert report == {"platform.idempotency_keys": 1, "platform.jobs": 1, "platform.dead_jobs": 1}

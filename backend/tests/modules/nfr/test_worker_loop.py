"""Worker ``run`` loop, graceful stop, and the periodic scheduler tick."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.nfr import JobContext, enqueue
from app.modules.nfr.internal.models import Job
from app.modules.nfr.internal.services import scheduler
from app.modules.nfr.internal.services.runner import Worker, WorkerConfig, default_worker_id
from app.shared.dhaka_date import DHAKA

pytestmark = pytest.mark.db


async def test_run_until_stopped(
    session: AsyncSession, sessions: Callable[[], AsyncSession], clock: FrozenClock
) -> None:
    stop = asyncio.Event()
    done: list[int] = []

    async def handler(_ctx: JobContext, payload: dict[str, Any]) -> None:
        done.append(payload["n"])
        if len(done) == 2:
            stop.set()

    for n in (1, 2):
        await enqueue(session, "x.do", {"n": n}, now=clock.now())
    config = WorkerConfig(queues=("default",), batch=1, busy_poll_s=0, idle_poll_s=0.01)
    await asyncio.wait_for(Worker(sessions, {"x.do": handler}, config, clock=clock).run(stop), 5)
    assert sorted(done) == [1, 2]
    assert ":" in default_worker_id()


async def test_loop_survives_iteration_errors(clock: FrozenClock) -> None:
    calls = 0

    def broken() -> AsyncSession:
        nonlocal calls
        calls += 1
        if calls >= 3:
            stop.set()
        raise ConnectionError("db down")

    stop = asyncio.Event()
    config = WorkerConfig(queues=("default",), idle_poll_s=0.01, renew_every_s=0.01)
    w = Worker(broken, {}, config, clock=clock)
    w.in_flight.add(Job(id=None))
    await asyncio.wait_for(w.run(stop), 5)
    assert calls >= 3


async def test_scheduler_enqueues_each_slot_once(session: AsyncSession) -> None:
    now = datetime(2026, 1, 15, 6, 30, tzinfo=UTC)
    assert await scheduler.tick(session, now) == 2
    assert await scheduler.tick(session, now) == 0
    assert await scheduler.tick(session, now + timedelta(hours=1)) == 1
    rows = (await session.execute(select(Job).order_by(Job.kind, Job.run_at))).scalars().all()
    partitions = next(r for r in rows if r.kind == "platform.partition.maintain")
    assert partitions.queue == "maintenance"
    assert partitions.run_at == datetime(2026, 1, 15, 2, 0, tzinfo=DHAKA)
    assert partitions.dedupe_key == "partitions:2026-01-15"
    assert [r.dedupe_key for r in rows if r.kind == "platform.retention.purge"] == [
        "retention:20260115T06",
        "retention:20260115T07",
    ]


def test_register_periodic_rejects_duplicates() -> None:
    job = scheduler.Periodic("test.periodic", "default", scheduler.hourly("t"))
    scheduler.register_periodic(job)
    try:
        with pytest.raises(ValueError, match="twice"):
            scheduler.register_periodic(job)
    finally:
        scheduler.PERIODIC.remove(job)

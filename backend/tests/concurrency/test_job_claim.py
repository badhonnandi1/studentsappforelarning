"""Parallel workers never run the same job twice; parallel relays never share an outbox row."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.clock import FrozenClock
from app.core.db import make_sessionmaker
from app.modules.nfr import JobContext, enqueue, publish
from app.modules.nfr.internal.models import Job, OutboxEvent
from app.modules.nfr.internal.repositories.outbox import fetch_unrelayed
from app.modules.nfr.internal.services.runner import Worker, WorkerConfig
from tests.modules.nfr.test_events import event

pytestmark = pytest.mark.concurrency
JOBS, WORKERS = 1000, 8  # 05 §F.1 item 6


async def test_workers_claim_each_job_once(committed_engine: AsyncEngine) -> None:
    sessions = make_sessionmaker(committed_engine)
    clock = FrozenClock(datetime(2026, 1, 15, tzinfo=UTC))
    async with sessions() as session, session.begin():
        for n in range(JOBS):
            await enqueue(session, "x.count", {"n": n}, now=clock.now() - timedelta(seconds=1))
    runs: Counter[int] = Counter()

    async def handler(_ctx: JobContext, payload: dict[str, Any]) -> None:
        runs[payload["n"]] += 1
        await asyncio.sleep(0)

    async def drain(name: str) -> None:
        config = WorkerConfig(queues=("default",), batch=10, recover_every_s=3600)
        worker = Worker(sessions, {"x.count": handler}, config, clock=clock, worker_id=name)
        while await worker.run_once():
            pass

    await asyncio.gather(*(drain(f"w{i}") for i in range(WORKERS)))
    assert sorted(runs) == list(range(JOBS))
    assert set(runs.values()) == {1}
    async with sessions() as session:
        assert (await session.execute(select(func.count()).select_from(Job))).scalar_one() == 0


async def test_killed_workers_jobs_complete_after_lease_expiry(
    committed_engine: AsyncEngine,
) -> None:
    sessions = make_sessionmaker(committed_engine)
    clock = FrozenClock(datetime(2026, 1, 15, tzinfo=UTC))
    async with sessions() as session, session.begin():
        for n in range(50):
            await enqueue(session, "x.count", {"n": n}, now=clock.now() - timedelta(seconds=1))
    runs: Counter[int] = Counter()

    async def handler(_ctx: JobContext, payload: dict[str, Any]) -> None:
        runs[payload["n"]] += 1

    config = WorkerConfig(queues=("default",), batch=20, recover_every_s=0)
    killed = Worker(sessions, {"x.count": handler}, config, clock=clock, worker_id="killed")
    held = await killed.claim()  # claims a batch, then dies before running it
    assert len(held) == 20
    survivor = Worker(sessions, {"x.count": handler}, config, clock=clock, worker_id="survivor")
    while await survivor.run_once():
        pass
    assert len(runs) == 30  # the killed worker's jobs wait for their lease
    clock.advance(config.lease + timedelta(seconds=1))
    while await survivor.run_once():
        pass
    assert sorted(runs) == list(range(50))
    assert set(runs.values()) == {1}


async def test_relays_lock_disjoint_rows(committed_engine: AsyncEngine) -> None:
    sessions = make_sessionmaker(committed_engine)
    async with sessions() as session, session.begin():
        for _ in range(20):
            await publish(session, event())
    async with sessions() as first, sessions() as second, first.begin(), second.begin():
        a = {row.id for row in await fetch_unrelayed(first, 12)}
        b = {row.id for row in await fetch_unrelayed(second, 12)}
    assert len(a) == 12
    assert len(b) == 8
    assert a.isdisjoint(b)
    async with sessions() as session:
        total = (await session.execute(select(func.count()).select_from(OutboxEvent))).scalar_one()
    assert total == 20

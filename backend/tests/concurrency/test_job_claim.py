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
JOBS, WORKERS = 200, 4


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
        config = WorkerConfig(queues=("default",), batch=5, recover_every_s=3600)
        worker = Worker(sessions, {"x.count": handler}, config, clock=clock, worker_id=name)
        while await worker.run_once():
            pass

    await asyncio.gather(*(drain(f"w{i}") for i in range(WORKERS)))
    assert sorted(runs) == list(range(JOBS))
    assert set(runs.values()) == {1}
    async with sessions() as session:
        assert (await session.execute(select(func.count()).select_from(Job))).scalar_one() == 0


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

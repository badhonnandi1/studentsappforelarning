"""Job queue: enqueue rules, SKIP LOCKED claim order, completion, retry, dead-lettering."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.nfr import JobContext, enqueue
from app.modules.nfr.internal.models import DeadJob, Job
from app.modules.nfr.internal.repositories import jobs as repo
from app.modules.nfr.internal.services.runner import Worker, WorkerConfig

pytestmark = pytest.mark.db
Factory = Callable[[], AsyncSession]


def worker(sessions: Factory, clock: FrozenClock, handlers: dict[str, Any]) -> Worker:
    config = WorkerConfig(queues=("default",), batch=1, recover_every_s=0)
    return Worker(sessions, handlers, config, clock=clock, worker_id="w1")


async def count(session: AsyncSession, model: type[Any]) -> int:
    return int((await session.execute(select(func.count()).select_from(model))).scalar_one())


async def test_enqueue_validates_and_dedupes(session: AsyncSession, clock: FrozenClock) -> None:
    now = clock.now()
    first = await enqueue(session, "x.do", {}, now=now, dedupe_key="k1")
    assert first is not None
    assert await enqueue(session, "x.do", {}, now=now, dedupe_key="k1") is None
    with pytest.raises(ValueError, match="unknown queue"):
        await enqueue(session, "x.do", {}, now=now, queue="nope")
    with pytest.raises(ValueError, match="priority"):
        await enqueue(session, "x.do", {}, now=now, priority=101)
    with pytest.raises(ValueError, match="dedupe_key"):
        await enqueue(session, "x.do", {}, now=now, dedupe_until=now)


async def test_claim_order_and_filters(session: AsyncSession, clock: FrozenClock) -> None:
    now = clock.now()
    low = await enqueue(session, "a", {}, now=now, priority=-5)
    high = await enqueue(session, "b", {}, now=now, priority=50)
    await enqueue(session, "c", {}, now=now, run_at=now + timedelta(minutes=5))
    await enqueue(session, "d", {}, now=now, queue="sms")
    claimed = await repo.claim_jobs(session, ["default"], 10, "w1", now, timedelta(seconds=60))
    assert [job.id for job in claimed] == [high, low]
    assert all(j.status == "running" and j.attempts == 1 and j.locked_by == "w1" for j in claimed)
    assert await repo.claim_jobs(session, ["default"], 10, "w1", now, timedelta(seconds=60)) == []


async def test_success_deletes_or_keeps_keyed_job(
    session: AsyncSession, sessions: Factory, clock: FrozenClock
) -> None:
    seen: list[JobContext] = []

    async def handler(ctx: JobContext, payload: dict[str, Any]) -> None:
        seen.append(ctx)
        assert payload == {"n": 1}

    now = clock.now()
    plain = await enqueue(session, "x.do", {"n": 1}, now=now)
    keyed = await enqueue(
        session, "x.do", {"n": 1}, now=now, dedupe_key="day:1", dedupe_until=now + timedelta(days=1)
    )
    w = worker(sessions, clock, {"x.do": handler})
    assert await w.run_once() == 1
    assert await w.run_once() == 1
    assert [ctx.attempt for ctx in seen] == [1, 1]
    assert await session.get(Job, plain, populate_existing=True) is None
    kept = await session.get(Job, keyed, populate_existing=True)
    assert kept is not None
    assert kept.status == "done"
    assert await w.run_once() == 0


async def test_failure_rolls_back_and_retries_with_backoff(
    session: AsyncSession, sessions: Factory, clock: FrozenClock
) -> None:
    async def handler(ctx: JobContext, _payload: dict[str, Any]) -> None:
        await enqueue(ctx.session, "side.effect", {}, now=ctx.now)
        raise RuntimeError("boom")

    job_id = await enqueue(session, "x.fail", {}, now=clock.now())
    assert await worker(sessions, clock, {"x.fail": handler}).run_once() == 1
    job = await session.get(Job, job_id, populate_existing=True)
    assert job is not None
    assert job.status == "queued"
    assert job.attempts == 1
    assert job.last_error == "RuntimeError: boom"
    assert timedelta(seconds=4) <= job.run_at - clock.now() <= timedelta(seconds=6)
    assert await count(session, Job) == 1  # the side effect rolled back


async def test_exhausted_attempts_and_unknown_kind_dead_letter(
    session: AsyncSession, sessions: Factory, clock: FrozenClock
) -> None:
    await enqueue(session, "x.unknown", {"a": 1}, now=clock.now(), max_attempts=1)
    assert await worker(sessions, clock, {}).run_once() == 1
    dead = (await session.execute(select(DeadJob))).scalar_one()
    assert dead.kind == "x.unknown"
    assert dead.payload == {"a": 1}
    assert dead.attempts == 1
    assert "no handler registered" in dead.last_error
    assert await count(session, Job) == 0


async def test_lease_recovery(session: AsyncSession, sessions: Factory, clock: FrozenClock) -> None:
    now = clock.now()
    retry = await enqueue(session, "x.slow", {}, now=now)
    last = await enqueue(session, "x.slow", {}, now=now, max_attempts=1)
    await repo.claim_jobs(session, ["default"], 10, "dead-worker", now, timedelta(seconds=60))
    w = worker(sessions, clock, {})
    assert await w.recover() == 0
    clock.advance(seconds=61)
    assert await w.recover() == 2
    job = await session.get(Job, retry, populate_existing=True)
    assert job is not None
    assert job.status == "queued"
    assert job.last_error == "lease expired"
    assert await session.get(Job, last, populate_existing=True) is None
    assert await count(session, DeadJob) == 1


async def test_renew_extends_lease(
    session: AsyncSession, sessions: Factory, clock: FrozenClock
) -> None:
    await enqueue(session, "x.long", {}, now=clock.now())
    w = worker(sessions, clock, {})
    assert await w.renew() == 0
    claimed = await w.claim()
    w.in_flight.update(claimed)
    clock.advance(seconds=30)
    assert await w.renew() == 1
    job = await session.get(Job, claimed[0].id, populate_existing=True)
    assert job is not None
    assert job.locked_until == clock.now() + timedelta(seconds=60)

"""The worker process runs jobs, relays the outbox and schedules periodic jobs together."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.clock import FrozenClock
from app.core.db import make_sessionmaker
from app.modules import nfr
from app.modules.nfr.internal.models import Job, OutboxEvent
from app.modules.nfr.internal.services.runner import WorkerConfig
from tests.modules.nfr.test_events import event

pytestmark = pytest.mark.concurrency


class MemorySink:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        assert content_type
        self.objects[f"{bucket}/{key}"] = body


async def test_worker_relay_and_scheduler_run_together(committed_engine: AsyncEngine) -> None:
    sessions = make_sessionmaker(committed_engine)
    clock = FrozenClock(datetime.now(UTC))
    ran: list[int] = []
    done = asyncio.Event()

    async def handler(_ctx: nfr.JobContext, payload: dict[str, Any]) -> None:
        ran.append(payload["n"])
        if len(ran) == 3:
            done.set()

    async with sessions() as session, session.begin():
        for n in range(3):
            await nfr.enqueue(session, "x.work", {"n": n}, now=clock.now())
        await nfr.publish(session, event())
    sink, stop = MemorySink(), asyncio.Event()
    config = WorkerConfig(queues=("default",), busy_poll_s=0.01, idle_poll_s=0.02)
    process = asyncio.create_task(
        nfr.run_worker_process(
            sessions,
            {"x.work": handler},
            ("default",),
            stop,
            relay=nfr.RelayTarget(sink, "events"),
            clock=clock,
            config=config,
            scheduler_every_s=0.05,
        )
    )
    await asyncio.wait_for(done.wait(), 10)
    for _ in range(100):
        if sink.objects:
            break
        await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(process, 10)
    assert sorted(ran) == [0, 1, 2]
    assert len(sink.objects) == 1
    async with sessions() as session:
        pending = (
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.relayed_at.is_(None))
        )
        assert (await session.execute(pending)).scalar_one() == 0
        kinds = set((await session.execute(select(Job.kind))).scalars())
    assert {"platform.partition.maintain", "platform.retention.purge"} <= kinds


async def test_rejects_unknown_queue_and_reports_missing_handlers() -> None:
    with pytest.raises(ValueError, match="unknown queues: nope"):
        await nfr.run_worker_process(lambda: None, {}, ("nope",), asyncio.Event())  # type: ignore[arg-type,return-value]
    assert nfr.unknown_queues(("default", "x")) == ["x"]
    assert "platform.retention.purge" in nfr.missing_handlers({})
    assert nfr.missing_handlers(nfr.job_handlers()) == []

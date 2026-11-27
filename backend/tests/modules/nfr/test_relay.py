"""Outbox relay to S3 Parquet, consumer batching and ``processed_events`` dedupe."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.settings import Settings
from app.core.storage import Storage
from app.modules.nfr import EventEnvelope, publish
from app.modules.nfr.contracts.jobs import JobContext
from app.modules.nfr.internal.jobs import relay
from app.modules.nfr.internal.jobs.parquet_writer import object_key, read_parquet
from app.modules.nfr.internal.models import Job, OutboxEvent, ProcessedEvent
from app.modules.nfr.internal.repositories.outbox import get_checkpoint
from app.modules.nfr.internal.services.consumer import (
    ConsumerSpec,
    consumer,
    consumers,
    job_handler,
    unregister,
)
from tests.modules.nfr.test_events import event

pytestmark = [pytest.mark.db, pytest.mark.integration]
BUCKET = "sp-test-events"
seen: list[list[EventEnvelope]] = []


async def record(_session: AsyncSession, events: list[EventEnvelope]) -> None:
    seen.append(events)


SPEC = ConsumerSpec("test_counter", frozenset({"test.thing_happened"}), "default", record)


@pytest.fixture
async def storage() -> Storage:
    store = Storage(Settings(_env_file=None))
    await store.ensure_bucket(BUCKET)
    return store


async def publish_n(session: AsyncSession, n: int) -> list[EventEnvelope]:
    async with session.begin():
        return [await publish(session, event()) for _ in range(n)]


async def test_relay_writes_parquet_jobs_and_checkpoint(
    session: AsyncSession,
    sessions: Callable[[], AsyncSession],
    storage: Storage,
    clock: FrozenClock,
) -> None:
    sent = await publish_n(session, 3)
    async with sessions() as relay_session:
        assert await relay.relay_once(relay_session, storage, BUCKET, [SPEC], clock) == 3
    key = object_key(sent)
    table = read_parquet(await storage.get_object(BUCKET, key))
    assert table.column("event_id").to_pylist() == [str(e.event_id) for e in sent]
    job = (await session.execute(select(Job))).scalar_one()
    assert job.kind == "consumer.test_counter"
    assert job.dedupe_key == f"test_counter:{sent[0].event_id}:{sent[-1].event_id}"
    assert len(job.payload["events"]) == 3
    rows = (await session.execute(select(OutboxEvent))).scalars().all()
    assert all(r.relayed_at == clock.now() and r.relay_attempts == 1 for r in rows)
    checkpoint = await get_checkpoint(session, "outbox")
    assert checkpoint is not None
    assert checkpoint.s3_object_key == key
    async with sessions() as relay_session:
        assert await relay.relay_once(relay_session, storage, BUCKET, [SPEC], clock) == 0


async def test_consumer_jobs_are_batched_by_500(session: AsyncSession, clock: FrozenClock) -> None:
    events = [event() for _ in range(501)]
    other = ConsumerSpec("other", frozenset({"test.unrelated"}), "default", record)
    async with session.begin():
        assert await relay.route_to_consumers(session, events, [SPEC, other], clock) == 2
        assert await relay.route_to_consumers(session, events, [SPEC], clock) == 0  # deduped
    sizes = sorted(len(j.payload["events"]) for j in (await session.execute(select(Job))).scalars())
    assert sizes == [1, 500]


async def test_consumer_runs_once_per_batch(session: AsyncSession, clock: FrozenClock) -> None:
    seen.clear()
    events = [event(), event()]
    payload = {"events": [e.model_dump(mode="json") for e in events]}
    handle = job_handler(SPEC)
    for attempt in (1, 2):
        async with session.begin():
            await handle(
                JobContext(events[0].event_id, SPEC.kind, "default", attempt, session, clock.now()),
                payload,
            )
    assert len(seen) == 1
    assert [e.event_id for e in seen[0]] == [e.event_id for e in events]
    row = (await session.execute(select(ProcessedEvent))).scalar_one()
    assert row.consumer == "test_counter"
    assert row.relay_batch_id is not None


def test_consumer_registry() -> None:
    decorated = consumer("test_reg", ["test.thing_happened"])(record)
    try:
        assert any(spec.name == "test_reg" for spec in consumers())
        with pytest.raises(ValueError, match="twice"):
            consumer("test_reg", [])(publish_n)  # type: ignore[arg-type]
        assert decorated is record
    finally:
        unregister("test_reg")


async def test_run_relay_loop_stops(
    sessions: Callable[[], AsyncSession], storage: Storage, clock: FrozenClock
) -> None:
    stop = asyncio.Event()
    calls = 0

    def specs() -> list[ConsumerSpec]:
        nonlocal calls
        calls += 1
        if calls == 2:
            stop.set()
            raise RuntimeError("bad registry")  # the loop logs and keeps going until stopped
        return [SPEC]

    await asyncio.wait_for(relay.run_relay(sessions, storage, BUCKET, specs, clock, stop), 5)
    assert calls == 2

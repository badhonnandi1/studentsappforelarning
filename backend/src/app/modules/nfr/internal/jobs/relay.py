"""Outbox relay (B.4, C.7): unrelayed rows → Parquet in S3 → consumer jobs → mark relayed.

One batch is up to 1,000 events. Each consumer gets **one job per ≤ 500 matching events**
(never one job per event) with ``dedupe_key = <consumer>:<first_id>:<last_id>``. The rows stay
locked (``FOR UPDATE SKIP LOCKED``) from read to commit, so parallel relays never share a row; a
crash before commit leaves the rows unrelayed and the rerun overwrites the same S3 object.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Sequence
from typing import Protocol

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock
from app.core.telemetry import counter
from app.modules.nfr.contracts.events import EventEnvelope
from app.modules.nfr.internal.jobs.parquet_writer import object_key, to_parquet
from app.modules.nfr.internal.repositories import outbox as repo
from app.modules.nfr.internal.services.consumer import BATCH_SIZE, ConsumerSpec, batch_id
from app.modules.nfr.internal.services.enqueue import enqueue

log = structlog.get_logger(__name__)
RELAY_NAME = "outbox"
RELAY_BATCH = 1000
BUSY_POLL_S, IDLE_POLL_S = 0.25, 1.0


class EventSink(Protocol):
    async def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None: ...


def chunks(events: Sequence[EventEnvelope], size: int) -> list[list[EventEnvelope]]:
    return [list(events[i : i + size]) for i in range(0, len(events), size)]


async def route_to_consumers(
    session: AsyncSession,
    events: Sequence[EventEnvelope],
    specs: Sequence[ConsumerSpec],
    clock: Clock,
) -> int:
    created = 0
    for spec in specs:
        matching = [e for e in events if e.type in spec.event_types]
        for chunk in chunks(matching, BATCH_SIZE):
            job_id = await enqueue(
                session,
                spec.kind,
                {"events": [e.model_dump(mode="json") for e in chunk]},
                now=clock.now(),
                queue=spec.queue,
                dedupe_key=f"{spec.name}:{batch_id(chunk)}",
            )
            created += job_id is not None
    return created


async def relay_once(
    session: AsyncSession,
    sink: EventSink,
    bucket: str,
    specs: Sequence[ConsumerSpec],
    clock: Clock,
    batch: int = RELAY_BATCH,
) -> int:
    """Relay one batch in one transaction. Return the number of events relayed."""
    async with session.begin():
        rows = await repo.fetch_unrelayed(session, batch)
        if not rows:
            return 0
        events = [repo.to_envelope(row) for row in rows]
        key = object_key(events)
        await sink.put_object(bucket, key, to_parquet(events), "application/vnd.apache.parquet")
        jobs = await route_to_consumers(session, events, specs, clock)
        now = clock.now()
        await repo.mark_relayed(session, [(r.id, r.recorded_on) for r in rows], now)
        await repo.save_checkpoint(session, RELAY_NAME, rows[-1], key, now)
    counter("app_outbox_relayed_total").add(len(rows))
    log.info("outbox_relayed", events=len(rows), jobs=jobs, object_key=key)
    return len(rows)


async def run_relay(
    sessions: Callable[[], AsyncSession],
    sink: EventSink,
    bucket: str,
    specs: Callable[[], Sequence[ConsumerSpec]],
    clock: Clock,
    stop: asyncio.Event,
) -> None:
    """The dedicated relay loop: every 250 ms while there is work, every 1 s when idle."""
    while not stop.is_set():
        try:
            async with sessions() as session:
                relayed = await relay_once(session, sink, bucket, specs(), clock)
        except Exception:
            log.exception("outbox_relay_failed")
            relayed = 0
        pause = BUSY_POLL_S if relayed else IDLE_POLL_S
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), pause)

"""One worker process: the job worker, the outbox relay loop and the periodic scheduler.

All three stop on the same event; the current job batch and relay batch always finish first.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.jobs.queues import QUEUES
from app.modules.nfr.contracts.jobs import JobHandler
from app.modules.nfr.internal.jobs.relay import EventSink, run_relay
from app.modules.nfr.internal.services import scheduler
from app.modules.nfr.internal.services.consumer import consumers
from app.modules.nfr.internal.services.runner import Worker, WorkerConfig

log = structlog.get_logger(__name__)
SCHEDULER_EVERY_S = 30.0
SessionFactory = Callable[[], AsyncSession]


@dataclass(frozen=True)
class RelayTarget:
    sink: EventSink
    bucket: str


def unknown_queues(queues: tuple[str, ...]) -> list[str]:
    return [q for q in queues if q not in QUEUES]


def missing_handlers(handlers: Mapping[str, JobHandler]) -> list[str]:
    """Periodic job kinds that no registered handler would run."""
    return [p.kind for p in scheduler.PERIODIC if p.kind not in handlers]


async def run_scheduler(
    sessions: SessionFactory, clock: Clock, stop: asyncio.Event, every_s: float
) -> None:
    """Enqueue due periodic jobs; ``dedupe_key`` keeps several schedulers from doubling them."""
    while not stop.is_set():
        try:
            async with sessions() as session, session.begin():
                await scheduler.tick(session, clock.now())
        except Exception:
            log.exception("scheduler_tick_failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), every_s)


async def run_worker_process(
    sessions: SessionFactory,
    handlers: Mapping[str, JobHandler],
    queues: tuple[str, ...],
    stop: asyncio.Event,
    *,
    relay: RelayTarget | None = None,
    clock: Clock | None = None,
    config: WorkerConfig | None = None,
    scheduler_every_s: float = SCHEDULER_EVERY_S,
) -> None:
    bad = unknown_queues(queues)
    if bad:
        raise ValueError(f"unknown queues: {', '.join(bad)}")
    clock = clock or SystemClock()
    worker = Worker(sessions, handlers, config or WorkerConfig(queues=queues), clock=clock)
    tasks = [
        asyncio.create_task(worker.run(stop)),
        asyncio.create_task(run_scheduler(sessions, clock, stop, scheduler_every_s)),
    ]
    if relay is not None:
        tasks.append(
            asyncio.create_task(
                run_relay(sessions, relay.sink, relay.bucket, consumers, clock, stop)
            )
        )
    try:
        await asyncio.gather(*tasks)
    finally:
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)

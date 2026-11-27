"""``@consumer``: event handlers fed by the relay, deduplicated by ``processed_events``.

The relay turns each batch of up to 500 matching events into one job of kind
``consumer.<name>``. The wrapper inserts the ``processed_events`` row in the job's transaction
before calling the handler, so a redelivered job is a no-op and a failed handler rolls back both
its effects and the dedupe row.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nfr.contracts.events import EventEnvelope
from app.modules.nfr.contracts.jobs import JobContext, JobHandler
from app.modules.nfr.internal.models import ProcessedEvent

BATCH_SIZE = 500
ConsumerFn = Callable[[AsyncSession, list[EventEnvelope]], Awaitable[None]]


@dataclass(frozen=True)
class ConsumerSpec:
    name: str
    event_types: frozenset[str]
    queue: str
    handler: ConsumerFn

    @property
    def kind(self) -> str:
        return f"consumer.{self.name}"


_CONSUMERS: dict[str, ConsumerSpec] = {}


def consumer(
    name: str, event_types: Iterable[str], *, queue: str = "default"
) -> Callable[[ConsumerFn], ConsumerFn]:
    def register(fn: ConsumerFn) -> ConsumerFn:
        if name in _CONSUMERS and _CONSUMERS[name].handler is not fn:
            raise ValueError(f"consumer {name} registered twice")
        _CONSUMERS[name] = ConsumerSpec(name, frozenset(event_types), queue, fn)
        return fn

    return register


def consumers() -> list[ConsumerSpec]:
    return list(_CONSUMERS.values())


def unregister(name: str) -> None:
    """Tests only."""
    _CONSUMERS.pop(name, None)


def batch_id(events: list[EventEnvelope]) -> str:
    return f"{events[0].event_id}:{events[-1].event_id}"


async def claim_batch(session: AsyncSession, name: str, events: list[EventEnvelope]) -> bool:
    """Insert the dedupe row; False means this batch was already processed."""
    first = events[0]
    stmt = (
        insert(ProcessedEvent)
        .values(
            consumer=name,
            event_id=first.event_id,
            event_recorded_on=first.recorded_on,
            relay_batch_id=batch_id(events) if len(events) > 1 else None,
        )
        .on_conflict_do_nothing()
        .returning(ProcessedEvent.event_id)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


def job_handler(spec: ConsumerSpec) -> JobHandler:
    async def run(ctx: JobContext, payload: dict[str, Any]) -> None:
        events = [EventEnvelope.model_validate(e) for e in payload["events"]]
        if events and await claim_batch(ctx.session, spec.name, events):
            await spec.handler(ctx.session, events)

    return run


def consumer_job_handlers() -> dict[str, JobHandler]:
    return {spec.kind: job_handler(spec) for spec in consumers()}

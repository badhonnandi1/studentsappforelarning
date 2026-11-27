"""``platform.outbox`` SQL for producers and the relay."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy import select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nfr.contracts.events import EventEnvelope
from app.modules.nfr.internal.models import OutboxEvent, RelayCheckpoint


def to_row(envelope: EventEnvelope) -> OutboxEvent:
    return OutboxEvent(
        id=envelope.event_id,
        recorded_on=envelope.recorded_on,
        event_type=envelope.type,
        schema_version=envelope.schema_version,
        aggregate_type=envelope.aggregate_type,
        aggregate_id=envelope.aggregate_id,
        user_id=envelope.user_id,
        track_enrolment_id=envelope.track_enrolment_id,
        tenant_id=envelope.tenant_id,
        payload=envelope.payload,
        occurred_at=envelope.occurred_at,
        recorded_at=envelope.recorded_at,
    )


def to_envelope(row: OutboxEvent) -> EventEnvelope:
    return EventEnvelope(
        event_id=row.id,
        type=row.event_type,
        schema_version=row.schema_version,
        occurred_at=row.occurred_at,
        recorded_at=row.recorded_at,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        user_id=row.user_id,
        track_enrolment_id=row.track_enrolment_id,
        tenant_id=row.tenant_id,
        payload=row.payload,
    )


async def insert_event(session: AsyncSession, envelope: EventEnvelope) -> None:
    session.add(to_row(envelope))
    await session.flush()


async def fetch_unrelayed(session: AsyncSession, batch: int) -> list[OutboxEvent]:
    """Oldest unrelayed rows, locked with SKIP LOCKED so parallel relays never share a row."""
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.relayed_at.is_(None))
        .order_by(OutboxEvent.recorded_at, OutboxEvent.id)
        .limit(batch)
        .with_for_update(skip_locked=True)
    )
    return list((await session.execute(stmt)).scalars())


async def mark_relayed(
    session: AsyncSession, keys: Sequence[tuple[uuid.UUID, date]], now: datetime
) -> None:
    await session.execute(
        update(OutboxEvent)
        .where(tuple_(OutboxEvent.id, OutboxEvent.recorded_on).in_(list(keys)))
        .values(relayed_at=now, relay_attempts=OutboxEvent.relay_attempts + 1)
    )


async def save_checkpoint(
    session: AsyncSession, name: str, last: OutboxEvent, object_key: str, now: datetime
) -> None:
    values = {
        "last_recorded_at": last.recorded_at,
        "last_event_id": last.id,
        "s3_object_key": object_key,
        "updated_at": now,
    }
    stmt = insert(RelayCheckpoint).values(relay_name=name, **values)
    await session.execute(stmt.on_conflict_do_update(index_elements=["relay_name"], set_=values))


async def get_checkpoint(session: AsyncSession, name: str) -> RelayCheckpoint | None:
    return await session.get(RelayCheckpoint, name)

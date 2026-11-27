"""``publish``: write an event in the caller's transaction (outbox pattern, v2 §3.5)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.modules.nfr.contracts.events import EventEnvelope, validate_envelope
from app.modules.nfr.internal.repositories import outbox as repo


async def publish(session: AsyncSession, envelope: EventEnvelope) -> EventEnvelope:
    """Validate and insert. Must run inside the producer's open transaction."""
    if not session.in_transaction():
        raise RuntimeError("publish() needs the producer's transaction (outbox pattern)")
    validate_envelope(envelope)
    await repo.insert_event(session, envelope)
    return envelope


def make_event(
    event_type: str,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    now: datetime,
    occurred_at: datetime | None = None,
    user_id: uuid.UUID | None = None,
    track_enrolment_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    schema_version: int = 1,
) -> EventEnvelope:
    return EventEnvelope(
        event_id=uuid7(),
        type=event_type,
        schema_version=schema_version,
        occurred_at=occurred_at or now,
        recorded_at=now,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        user_id=user_id,
        track_enrolment_id=track_enrolment_id,
        tenant_id=tenant_id,
        payload=payload,
    )

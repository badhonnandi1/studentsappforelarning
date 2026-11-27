"""Event envelope validation and ``publish`` (outbox in the producer's transaction)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nfr import EventEnvelope, make_event, publish, register_payload
from app.modules.nfr.contracts.events import sensitive_paths, validate_envelope
from app.modules.nfr.internal.models import OutboxEvent

pytestmark = pytest.mark.db
NOW = datetime.now(UTC).replace(microsecond=0)  # outbox partitions exist from today


class ThingHappened(BaseModel):
    thing_id: uuid.UUID
    score: int = 0


register_payload("test.thing_happened", 1, ThingHappened)


def event(
    payload: dict[str, object] | None = None, kind: str = "test.thing_happened"
) -> EventEnvelope:
    thing = uuid.uuid4()
    return make_event(
        kind,
        aggregate_type="thing",
        aggregate_id=thing,
        payload=payload if payload is not None else {"thing_id": str(thing)},
        now=NOW,
    )


async def test_publish_writes_outbox_row(session: AsyncSession) -> None:
    async with session.begin():
        sent = await publish(session, event())
    row = (await session.execute(select(OutboxEvent))).scalar_one()
    assert row.id == sent.event_id
    assert row.recorded_on == NOW.date()
    assert row.event_type == "test.thing_happened"
    assert row.relayed_at is None


async def test_publish_requires_transaction(session: AsyncSession) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        await publish(session, event())


def test_envelope_rules() -> None:
    with pytest.raises(ValueError, match="unregistered"):
        validate_envelope(event(kind="test.unknown_thing"))
    with pytest.raises(ValidationError):
        validate_envelope(event({"thing_id": "not-a-uuid"}))
    with pytest.raises(ValueError, match="sensitive"):
        validate_envelope(event({"thing_id": str(uuid.uuid4()), "phone": "+8801712345678"}))
    with pytest.raises(ValidationError, match=r"module\.thing"):
        event(kind="BadType")
    with pytest.raises(ValidationError, match="timezone"):
        EventEnvelope(**{**event().model_dump(), "occurred_at": datetime(2026, 1, 1)})
    with pytest.raises(ValueError, match="already registered"):
        register_payload("test.thing_happened", 1, BaseModel)


def test_sensitive_paths_walk_nested_values() -> None:
    payload = {"a": [{"email": "x"}], "b": {"otp_code": 1}, "ok": 1}
    assert sensitive_paths(payload) == ["a[0].email", "b.otp_code"]

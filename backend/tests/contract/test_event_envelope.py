"""``user.signed_in`` as it lands in the outbox validates against ``EventEnvelope`` v1, and the
envelope and payload schemas match the committed golden files (05 §F test plan).

A schema change that consumers would see must be deliberate: bump ``schema_version`` or add an
optional field, then refresh the golden file with ``UPDATE_GOLDEN=1``."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.auth.contracts.events import USER_SIGNED_IN, UserSignedIn
from app.modules.nfr import EventEnvelope
from app.modules.nfr.internal.models import OutboxEvent
from app.modules.nfr.internal.repositories.outbox import to_envelope
from tests.support.full_app import STUDENT, student_session

pytestmark = [pytest.mark.contract, pytest.mark.db]
GOLDEN = Path(__file__).parent / "golden"


def matches_golden(name: str, model: type[BaseModel]) -> None:
    path = GOLDEN / f"{name}.schema.json"
    schema = json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1":
        path.write_text(schema)
    assert schema == path.read_text(), f"{name} schema changed; see this module's docstring"


def test_schemas_match_golden() -> None:
    matches_golden("event_envelope_v1", EventEnvelope)
    matches_golden("user_signed_in_v1", UserSignedIn)


async def test_signed_in_event_validates(
    wired: None, people: None, app_redis: Redis, session: AsyncSession, clock: FrozenClock
) -> None:
    del wired, people, app_redis
    _, session_id = await student_session(session, STUDENT, clock.now())
    async with session.begin():
        rows = (await session.execute(select(OutboxEvent))).scalars().all()
    (row,) = [r for r in rows if r.event_type == USER_SIGNED_IN]
    wire: dict[str, Any] = json.loads(to_envelope(row).model_dump_json())
    envelope = EventEnvelope.model_validate(wire)
    assert envelope.schema_version == 1
    assert envelope.user_id == STUDENT
    assert envelope.aggregate_type == "user"
    payload = UserSignedIn.model_validate(envelope.payload)
    assert payload.session_id == session_id
    assert (payload.method, payload.platform, payload.created) == ("otp", "android", False)
    assert set(wire) == set(EventEnvelope.model_fields)

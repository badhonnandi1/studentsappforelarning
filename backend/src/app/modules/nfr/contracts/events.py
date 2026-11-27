"""The event envelope shared by every event (v2 §3.3) and the payload schema registry.

A producer registers the payload model for each ``(type, schema_version)``; ``publish`` refuses
unregistered types, so every event in the S3 log has a known shape.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.logging import is_sensitive

EVENT_TYPE = re.compile(r"^[a-z_]+\.[a-z_.]+$")
_PAYLOADS: dict[tuple[str, int], type[BaseModel]] = {}


class EventEnvelope(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: uuid.UUID
    type: str
    schema_version: int = Field(default=1, gt=0)
    occurred_at: datetime
    recorded_at: datetime
    aggregate_type: str
    aggregate_id: uuid.UUID
    user_id: uuid.UUID | None = None
    track_enrolment_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    payload: dict[str, Any]

    @field_validator("type")
    @classmethod
    def _type(cls, value: str) -> str:
        if not EVENT_TYPE.match(value):
            raise ValueError("event type must look like 'module.thing_happened'")
        return value

    @field_validator("occurred_at", "recorded_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("event timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @property
    def recorded_on(self) -> date:
        """The UTC date of ``recorded_at``: the outbox and processed_events partition key."""
        return self.recorded_at.date()


def register_payload(event_type: str, version: int, model: type[BaseModel]) -> None:
    existing = _PAYLOADS.get((event_type, version))
    if existing is not None and existing is not model:
        raise ValueError(f"{event_type} v{version} already registered")
    _PAYLOADS[(event_type, version)] = model


def payload_model(event_type: str, version: int) -> type[BaseModel] | None:
    return _PAYLOADS.get((event_type, version))


def sensitive_paths(value: Any, path: str = "") -> list[str]:
    """Keys that look like PII or secrets (phone, email, token, otp …), anywhere in the payload."""
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{path}.{key}" if path else str(key)
            if is_sensitive(str(key)):
                found.append(here)
            found.extend(sensitive_paths(item, here))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(sensitive_paths(item, f"{path}[{index}]"))
    return found


def validate_envelope(envelope: EventEnvelope) -> None:
    model = payload_model(envelope.type, envelope.schema_version)
    if model is None:
        raise ValueError(f"unregistered event {envelope.type} v{envelope.schema_version}")
    model.model_validate(envelope.payload)
    leaked = sensitive_paths(envelope.payload)
    if leaked:
        raise ValueError(f"event payload carries sensitive keys: {', '.join(leaked)}")

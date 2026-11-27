"""Schemas for ``/v1/admin/audit-log`` and ``/v1/admin/runtime-config``."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class AuditEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_kind: str
    actor_roles: list[str]
    action: str
    module: str
    target_type: str
    target_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    request_id: str | None
    tenant_id: uuid.UUID | None


class RuntimeConfigIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: JsonValue
    reason: str = Field(min_length=3, max_length=500)


class RuntimeConfigOut(BaseModel):
    key: str
    value: JsonValue
    updated_at: datetime

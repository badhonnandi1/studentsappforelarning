"""``/v1/me`` models (05 §D)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.modules.auth.internal.schemas.auth import DisplayName, In, UserSummary

FirstName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=30, pattern=r"^[A-Za-zÀ-ɏঀ-৿ ]+$"),
]


class IdentityItem(BaseModel):
    provider: str
    linked_at: datetime


class ConsentState(BaseModel):
    required: bool
    status: Literal["granted", "missing", "not_required"]


class MeOut(UserSummary):
    phone_masked: str | None
    identities: list[IdentityItem]
    consent: ConsentState


class MePatchIn(In):
    display_name: DisplayName | None = None
    first_name: FirstName | None = None
    locale: Literal["bn", "en"] | None = None


class SessionOut(BaseModel):
    session_id: uuid.UUID
    platform: str
    app_version: str | None
    model: str | None
    created_at: datetime
    last_seen_at: datetime
    current: bool

"""Privacy settings, guardian consent and consent document DTOs (05 §D)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.modules.auth.internal.schemas.auth import In, OtpCode

Lang = Literal["bn", "en"]
Relation = Literal["mother", "father", "guardian", "other"]
Version = Annotated[str, StringConstraints(pattern=r"^[0-9a-z-]{1,40}$")]


class PrivacyIn(In):
    leaderboard_visible: bool | None = None
    profile_private: bool | None = None


class PrivacyOut(BaseModel):
    leaderboard_visible: bool
    profile_private: bool
    opt_out_by: Literal["self", "guardian"] | None


class GuardianStartIn(In):
    guardian_phone: Annotated[str, StringConstraints(max_length=32)]
    guardian_relation: Relation
    consent_version: Version


class GuardianStartOut(BaseModel):
    challenge_id: uuid.UUID
    expires_at: datetime


class GuardianConfirmIn(In):
    challenge_id: uuid.UUID
    code: OtpCode


class ConsentOut(BaseModel):
    status: Literal["granted"]
    version: str
    granted_at: datetime


class GuardianConfirmOut(BaseModel):
    consent: ConsentOut


class ConsentDocumentOut(BaseModel):
    version: str
    lang: Lang
    body_markdown: str
    published_at: datetime

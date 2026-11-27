"""COM request and response bodies (05 §D)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints

Category = Literal["profanity", "sexual", "hate", "self_harm", "contact_info", "spam"]
SEVERITY = {"low": 1, "medium": 2, "high": 3}
SEVERITY_NAME = {v: k for k, v in SEVERITY.items()}
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TermIn(In):
    lang: Literal["bn", "en", "banglish"]
    term: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    severity: Literal["low", "medium", "high"] = "medium"
    category: Category


class TermOut(BaseModel):
    id: uuid.UUID
    lang: str
    term_folded: str
    severity: str
    category: str
    is_active: bool
    created_at: datetime


class ReportIn(In):
    target_type: Literal["user", "display_name", "profile_photo", "post", "other"]
    target_id: uuid.UUID
    reason: Literal["abuse", "spam", "sexual", "self_harm", "privacy", "cheating", "other"]
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class ReportCreated(BaseModel):
    report_id: uuid.UUID


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reporter_user_id: uuid.UUID
    target_type: str
    target_id: str
    reason: str
    text: str | None
    status: str
    resolved_by: uuid.UUID | None
    resolved_at: datetime | None
    created_at: datetime


class RestrictionIn(In):
    user_id: uuid.UUID
    kind: Literal["mute", "ban"]
    scope: Literal["all", "community", "profile"] = "all"
    reason: Note
    ends_at: AwareDatetime | None = None


class RestrictionInput(In):
    """A restriction applied while resolving a report; the user is the report's target."""

    kind: Literal["mute", "ban"]
    scope: Literal["all", "community", "profile"] = "all"
    ends_at: AwareDatetime | None = None


class ResolveIn(In):
    decision: Literal["dismiss", "action_taken"]
    note: Note
    restriction: RestrictionInput | None = None


class RestrictionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    scope: str
    reason: str
    starts_at: datetime
    ends_at: datetime | None
    lifted_at: datetime | None

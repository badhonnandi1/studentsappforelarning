"""Request and response models for ``/v1/auth/*`` (05 §D, 14 §2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

DeviceId = Annotated[str, StringConstraints(min_length=8, max_length=64, pattern=r"^[\w.:-]+$")]
OtpCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]
Opaque = Annotated[str, StringConstraints(min_length=16, max_length=256)]


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeviceInfo(In):
    device_id: DeviceId
    platform: Literal["android", "web", "ios"]
    app_version: Annotated[str, StringConstraints(max_length=32)] | None = None
    model: Annotated[str, StringConstraints(max_length=64)] | None = None


class OtpSendIn(In):
    phone: Annotated[str, StringConstraints(max_length=32)]
    purpose: Literal["sign_in"] = "sign_in"
    device_id: DeviceId
    challenge_token: Annotated[str, StringConstraints(max_length=4096)] | None = None


class OtpSendOut(BaseModel):
    challenge_id: uuid.UUID
    expires_at: datetime
    resend_after_s: int


class OtpVerifyIn(In):
    challenge_id: uuid.UUID
    code: OtpCode
    device: DeviceInfo


class UserSummary(BaseModel):
    id: uuid.UUID
    display_name: str | None
    first_name: str | None
    is_minor: bool
    roles: list[str]
    needs_consent: bool
    needs_profile: bool


class TokenPair(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    session_id: uuid.UUID
    user: UserSummary


class SignInOut(TokenPair):
    linked: bool = False
    created: bool = False


class NeedsProfileOut(BaseModel):
    status: Literal["needs_profile"] = "needs_profile"
    pending_signup_token: str
    required: list[str] = Field(default_factory=lambda: ["date_of_birth"])


DisplayName = Annotated[
    str,
    StringConstraints(min_length=2, max_length=40, pattern=r"^[A-Za-zÀ-ɏঀ-৿ ]+$"),
]


class SignUpCompleteIn(In):
    pending_signup_token: Opaque
    date_of_birth: date
    display_name: DisplayName | None = None


class RefreshIn(In):
    refresh_token: Opaque

"""Social sign-in and linked identity DTOs (05 §D)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.modules.auth.internal.schemas.auth import DeviceInfo, In

Provider = Literal["google", "facebook"]
ProviderToken = Annotated[str, StringConstraints(min_length=16, max_length=8192)]
Nonce = Annotated[str, StringConstraints(min_length=16, max_length=128)]


class NonceIn(In):
    provider: Provider


class NonceOut(BaseModel):
    nonce: str
    expires_at: datetime


class SocialSignInIn(In):
    token: ProviderToken
    nonce: Nonce
    device: DeviceInfo
    date_of_birth: date | None = None


class LinkIn(In):
    token: ProviderToken
    nonce: Nonce


class IdentityOut(BaseModel):
    provider: str
    display_name: str | None
    email_masked: str | None
    linked_at: datetime
    last_login_at: datetime | None


class IdentitiesOut(BaseModel):
    items: list[IdentityOut]
    phone_verified: bool

"""Events AUTH publishes through the outbox (v2 §3.3)."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.modules.nfr import register_payload

USER_SIGNED_IN = "user.signed_in"
SignInMethod = Literal["otp", "google", "facebook", "apple", "password", "sso"]
Platform = Literal["android", "web", "ios"]


class UserSignedIn(BaseModel):
    """``user_id`` is on the envelope. No phone, email or token ever appears here."""

    model_config = ConfigDict(extra="forbid")

    session_id: uuid.UUID
    method: SignInMethod
    platform: Platform
    created: bool


register_payload(USER_SIGNED_IN, 1, UserSignedIn)

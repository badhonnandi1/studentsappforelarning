"""Step-up OTP, second factor and phone change DTOs (05 §D, R-25)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.modules.auth.internal.schemas.auth import In, OtpCode

StepUpAction = Literal["unlink", "phone_change", "deletion", "guardian_change"]


class StepUpSendIn(In):
    action: StepUpAction


class StepUpIn(In):
    action: StepUpAction
    otp_challenge_id: uuid.UUID
    code: OtpCode


class StepUpOut(BaseModel):
    step_up_token: str
    expires_at: datetime


class SecondFactorOut(BaseModel):
    """Dormant account on a new device: sign in with a linked provider instead (R-25)."""

    status: Literal["second_factor_required"] = "second_factor_required"
    providers: list[str]


class PhoneStartIn(In):
    phone: str


class PhoneConfirmIn(In):
    challenge_id: uuid.UUID
    code: OtpCode


class ChallengeOut(BaseModel):
    challenge_id: uuid.UUID
    expires_at: datetime


class PhoneOut(BaseModel):
    phone_masked: str

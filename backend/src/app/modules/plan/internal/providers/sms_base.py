"""The ``SmsGateway`` port. Adapters never log or raise with the phone number or body."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class SendResult:
    provider_msg_id: str | None
    cost_poisha: int | None
    status: Literal["sent", "fake_sent"] = "sent"


class SmsGatewayError(Exception):
    """A send that may succeed on retry. Messages carry no phone numbers or bodies."""


class SmsGateway(Protocol):
    name: str

    async def send(self, to_phone: str, body: str) -> SendResult: ...

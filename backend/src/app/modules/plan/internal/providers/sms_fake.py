"""Fake gateway: records messages (status ``fake_sent``); logs the body in local and test only."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

from app.core.settings import Settings
from app.modules.plan.internal.providers.sms_base import SendResult

log = structlog.get_logger(__name__)
CODE = re.compile(r"\b(\d{4,8})\b")


@dataclass(frozen=True)
class FakeSms:
    to_phone: str
    body: str


@dataclass
class FakeSmsGateway:
    settings: Settings
    name: str = "fake"
    sent: list[FakeSms] = field(default_factory=list)

    async def send(self, to_phone: str, body: str) -> SendResult:
        self.sent.append(FakeSms(to_phone, body))
        if self.settings.app_env in ("local", "test"):
            log.info("fake_sms", sms_body=body)
        return SendResult(
            provider_msg_id=f"fake-{len(self.sent)}", cost_poisha=0, status="fake_sent"
        )

    def last_code(self, to_phone: str) -> str | None:
        """The last numeric code sent to this phone (tests and local development)."""
        for message in reversed(self.sent):
            if message.to_phone == to_phone:
                found = CODE.search(message.body)
                return found.group(1) if found else None
        return None

"""The process-wide SMS gateway, chosen by ``SMS_BACKEND``."""

from __future__ import annotations

from app.core.settings import get_settings
from app.modules.plan.internal.providers.sms_base import SmsGateway
from app.modules.plan.internal.providers.sms_fake import FakeSmsGateway
from app.modules.plan.internal.providers.sms_http import HttpSmsGateway

_gateway: SmsGateway | None = None


def gateway() -> SmsGateway:
    global _gateway
    if _gateway is None:
        settings = get_settings()
        _gateway = (
            FakeSmsGateway(settings) if settings.sms_backend == "fake" else HttpSmsGateway(settings)
        )
    return _gateway


def use_gateway(replacement: SmsGateway | None) -> None:
    global _gateway
    _gateway = replacement

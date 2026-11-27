"""CAPTCHA check required after repeated OTP failures (05 §C.4, 18 §2: Cloudflare Turnstile).

Deployed environments must set ``TURNSTILE_SECRET`` (settings validator). Locally, without a
secret, the token ``local-pass`` passes so the flow can be exercised end to end.
"""

from __future__ import annotations

from typing import Protocol

import httpx
import structlog

from app.core.errors import ForbiddenError, UnavailableError
from app.core.http_client import make_http_client
from app.core.settings import Settings, get_settings

log = structlog.get_logger(__name__)
SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
LOCAL_PASS = "local-pass"  # noqa: S105 - local/test only; deploys require TURNSTILE_SECRET


class CaptchaVerifier(Protocol):
    async def verify(self, token: str, ip: str) -> bool: ...


class TurnstileVerifier:
    def __init__(self, secret: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.secret, self.transport = secret, transport

    async def verify(self, token: str, ip: str) -> bool:
        data = {"secret": self.secret, "response": token, "remoteip": ip}
        try:
            async with make_http_client(transport=self.transport) as client:
                response = await client.post(SITEVERIFY, data=data)
                response.raise_for_status()
                return response.json().get("success") is True
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("captcha_verify_failed", error=type(exc).__name__)
            raise UnavailableError("The challenge service is unavailable") from exc


class LocalVerifier:
    async def verify(self, token: str, ip: str) -> bool:
        return bool(ip) and token == LOCAL_PASS


_override: CaptchaVerifier | None = None


def use_verifier(verifier: CaptchaVerifier | None) -> None:
    global _override
    _override = verifier


def verifier(settings: Settings | None = None) -> CaptchaVerifier:
    if _override is not None:
        return _override
    settings = settings or get_settings()
    secret = settings.turnstile_secret.get_secret_value()
    return TurnstileVerifier(secret) if secret else LocalVerifier()


async def require_challenge(token: str | None, ip: str) -> None:
    if token and await verifier().verify(token, ip):
        return
    raise ForbiddenError(
        "Complete the challenge to get a new code",
        code="challenge_required",
        details={"challenge_url": get_settings().otp_challenge_url},
    )

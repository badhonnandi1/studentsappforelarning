"""Turnstile verification used by ``challenge_required`` (18 §2)."""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.core.errors import ForbiddenError, UnavailableError
from app.core.settings import Settings
from app.modules.auth.internal.providers import captcha

pytestmark = pytest.mark.unit


def transport(status: int, body: object) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler), seen


async def test_turnstile_success_and_failure() -> None:
    ok, seen = transport(200, {"success": True})
    assert await captcha.TurnstileVerifier("s3cret", ok).verify("tok", "198.51.100.1")
    form = seen[0].content.decode()
    assert "secret=s3cret" in form
    assert "response=tok" in form
    assert "remoteip=198.51.100.1" in form
    assert str(seen[0].url) == captcha.SITEVERIFY
    no, _ = transport(200, {"success": False, "error-codes": ["invalid-input-response"]})
    assert not await captcha.TurnstileVerifier("s3cret", no).verify("tok", "ip")


async def test_turnstile_outage_is_unavailable() -> None:
    down, _ = transport(502, {})
    with pytest.raises(UnavailableError):
        await captcha.TurnstileVerifier("s3cret", down).verify("tok", "ip")


def test_verifier_choice() -> None:
    assert isinstance(captcha.verifier(Settings(_env_file=None)), captcha.LocalVerifier)
    configured = Settings(_env_file=None, turnstile_secret=SecretStr("x" * 32))
    assert isinstance(captcha.verifier(configured), captcha.TurnstileVerifier)


async def test_require_challenge() -> None:
    await captcha.require_challenge(captcha.LOCAL_PASS, "198.51.100.1")
    for token in (None, "", "wrong"):
        with pytest.raises(ForbiddenError) as raised:
            await captcha.require_challenge(token, "198.51.100.1")
        assert raised.value.code == "challenge_required"
    assert not await captcha.LocalVerifier().verify(captcha.LOCAL_PASS, "")

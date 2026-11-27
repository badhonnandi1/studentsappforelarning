"""Fake social providers for API tests: a known token maps to a fixed identity."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from app.core.settings import get_settings
from app.modules.auth.internal.providers import registry
from app.modules.auth.internal.providers.base import ProviderError, VerifiedIdentity

GOOGLE = VerifiedIdentity("google", "g-1", "kid@example.com", True, "Kid One")
FACEBOOK = VerifiedIdentity("facebook", "fb-1", "kid@example.com", False, "Kid One")


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tokens: dict[str, VerifiedIdentity] = {}

    async def verify(self, token: str, nonce: str) -> VerifiedIdentity:
        del nonce
        if token not in self.tokens:
            raise ProviderError()
        return self.tokens[token]


def token_for(provider: str) -> str:
    return f"{provider}-token-0000000000"


def install(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, FakeProvider]]:
    monkeypatch.setattr(get_settings(), "google_enabled", True)
    monkeypatch.setattr(get_settings(), "facebook_enabled", True)
    made = {name: FakeProvider(name) for name in ("google", "facebook")}
    made["google"].tokens[token_for("google")] = GOOGLE
    made["facebook"].tokens[token_for("facebook")] = FACEBOOK
    for name, fake in made.items():
        registry.use_provider(name, fake)
    yield made
    for name in made:
        registry.use_provider(name, None)


async def nonce(client: httpx.AsyncClient, provider: str) -> str:
    response = await client.post("/v1/auth/social/nonce", json={"provider": provider})
    return str(response.json()["nonce"])


async def provider_body(client: httpx.AsyncClient, provider: str, **extra: Any) -> dict[str, Any]:
    return {"token": token_for(provider), "nonce": await nonce(client, provider), **extra}

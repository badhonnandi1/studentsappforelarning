"""Provider edge paths: Redis down, malformed keys and bodies, registry construction."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from pydantic import SecretStr
from redis.asyncio import Redis
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from app.core.errors import NotFoundError, UnavailableError
from app.core.redis import use_client
from app.core.settings import get_settings
from app.modules.auth.internal.providers import registry
from app.modules.auth.internal.providers.base import ProviderError
from app.modules.auth.internal.providers.facebook import FacebookProvider
from app.modules.auth.internal.providers.google import GoogleProvider
from app.modules.auth.internal.providers.jwks import JwksCache
from app.modules.auth.internal.services import social_nonce
from tests.modules.auth.test_providers import CLIENT, NONCE, google_claims
from tests.support.oidc import KID, id_token, jwks_transport

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("app_redis")]


def redis_down() -> None:
    no_retry = Retry(NoBackoff(), 0)
    use_client(Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, retry=no_retry))


async def test_redis_down_nonce_is_503_and_keys_unavailable() -> None:
    redis_down()
    with pytest.raises(UnavailableError):
        await social_nonce.issue("google", datetime.now(UTC))
    with pytest.raises(UnavailableError):
        await social_nonce.consume("n" * 43, "google")
    cache = JwksCache("google", "https://keys.example/jwks", jwks_transport([]))
    assert await cache._cached() is None
    assert await cache._may_refetch() is True
    with pytest.raises(UnavailableError):  # the breaker itself needs Redis
        await cache.signing_key(KID)


async def test_malformed_keys_and_bodies() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/bad-jwk":
            return httpx.Response(200, json={"keys": [{"kid": KID, "kty": "RSA", "n": "x"}]})
        return httpx.Response(200, content=b"not json")

    transport = httpx.MockTransport(handler)
    with pytest.raises(ProviderError):
        await JwksCache("google", "https://k.example/bad-jwk", transport).signing_key(KID)
    with pytest.raises(ProviderError):
        await JwksCache("google", "https://k.example/text", transport).signing_key(KID)
    google = GoogleProvider([CLIENT], jwks_transport([]))
    with pytest.raises(ProviderError):
        await google.verify(id_token(**google_claims(email=["not", "a", "string"])), NONCE)


def test_registry_builds_configured_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "google_enabled", True)
    monkeypatch.setattr(settings, "facebook_enabled", True)
    monkeypatch.setattr(settings, "google_client_ids", [CLIENT])
    monkeypatch.setattr(settings, "facebook_app_id", "42")
    monkeypatch.setattr(settings, "facebook_app_secret", SecretStr("s3cret"))
    assert isinstance(registry.get("google"), GoogleProvider)
    assert isinstance(registry.get("facebook"), FacebookProvider)
    assert not registry.enabled("apple")
    with pytest.raises(NotFoundError):
        registry.get("apple")

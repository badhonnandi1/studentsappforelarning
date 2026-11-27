"""Google and Facebook token verification, JWKS caching, breaker fallback (05 §C.5)."""

from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis

from app.core.errors import UnavailableError
from app.modules.auth.internal.providers import jwks as jwks_mod
from app.modules.auth.internal.providers.base import ProviderError
from app.modules.auth.internal.providers.facebook import FacebookProvider, appsecret_proof
from app.modules.auth.internal.providers.google import GoogleProvider
from tests.support.oidc import id_token, jwks_transport

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("app_redis")]
NONCE = "n" * 43
CLIENT = "client-1.apps.googleusercontent.com"


def google_claims(**changes: Any) -> dict[str, Any]:
    claims = {"iss": "https://accounts.google.com", "aud": CLIENT, "sub": "g-123",
              "email": "Student@Example.com", "email_verified": True, "name": "A B",
              "nonce": NONCE}  # fmt: skip
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not None}


async def test_google_verifies_and_caches_keys() -> None:
    calls: list[str] = []
    google = GoogleProvider([CLIENT], jwks_transport(calls))
    ident = await google.verify(id_token(**google_claims()), NONCE)
    assert (ident.subject, ident.email, ident.email_verified) == (
        "g-123",
        "student@example.com",
        True,
    )
    await google.verify(id_token(**google_claims(iss="accounts.google.com")), NONCE)
    assert len(calls) == 1  # second key lookup came from Redis


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
        {"nonce": "x" * 43},
        {"nonce": None},
        {"exp": int(time.time()) - 10},
        {"iat": int(time.time()) + 600},
        {"sub": None},
    ],
)
async def test_google_rejects_bad_claims(changes: dict[str, Any]) -> None:
    google = GoogleProvider([CLIENT], jwks_transport([]))
    with pytest.raises(ProviderError):
        await google.verify(id_token(**google_claims(**changes)), NONCE)


async def test_google_rejects_bad_tokens() -> None:
    calls: list[str] = []
    google = GoogleProvider([CLIENT], jwks_transport(calls))
    for token in (
        "not-a-jwt",
        id_token(alg="HS256", **google_claims()),
        id_token(kid="other", **google_claims()),
    ):
        with pytest.raises(ProviderError):
            await google.verify(token, NONCE)
    with pytest.raises(ProviderError):
        await google.verify(id_token(kid="another", **google_claims()), NONCE)
    assert len(calls) == 1  # unknown kids refetch at most once per 30 s


async def test_unknown_kid_refetches_once(app_redis: Redis) -> None:
    calls: list[str] = []
    google = GoogleProvider([CLIENT], jwks_transport(calls))
    await app_redis.set(google.jwks.key, '{"keys": []}')  # stale cache without our key
    await google.verify(id_token(**google_claims()), NONCE)
    assert len(calls) == 1


async def test_provider_outage_is_503_with_fallback() -> None:
    google = GoogleProvider([CLIENT], jwks_transport([], status=503))
    with pytest.raises(UnavailableError) as raised:
        await google.verify(id_token(**google_claims()), NONCE)
    assert raised.value.details == {"fallback": "phone_otp"}
    broken = GoogleProvider([CLIENT], jwks_transport([], status=404))
    with pytest.raises(ProviderError):
        await broken.verify(id_token(**google_claims()), NONCE)


def test_ttl_and_constructor_guards() -> None:
    assert jwks_mod._ttl("public, max-age=19000") == 19000
    assert jwks_mod._ttl("max-age=5") == jwks_mod.MIN_TTL_S
    assert jwks_mod._ttl(None) == jwks_mod.DEFAULT_TTL_S
    with pytest.raises(ValueError, match="client id"):
        GoogleProvider([])
    with pytest.raises(ValueError, match="app id"):
        FacebookProvider("", "", "v27.0")


def graph(
    debug: dict[str, Any], me: dict[str, Any], seen: list[httpx.Request]
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = {"data": debug} if request.url.path.endswith("/debug_token") else me
        return httpx.Response(200, json=body)

    return httpx.MockTransport(handler)


VALID = {"is_valid": True, "app_id": "42", "user_id": "fb-9", "expires_at": int(time.time()) + 600}


async def test_facebook_access_token() -> None:
    seen: list[httpx.Request] = []
    me = {"id": "fb-9", "name": "F B", "email": "F@B.com"}
    fb = FacebookProvider("42", "s3cret", "v27.0", graph(VALID, me, seen))
    ident = await fb.verify("EAAB" + "t" * 40, NONCE)
    assert (ident.subject, ident.email, ident.email_verified) == ("fb-9", "f@b.com", False)
    assert seen[1].url.params["appsecret_proof"] == appsecret_proof("EAAB" + "t" * 40, "s3cret")
    assert seen[0].url.path == "/v27.0/debug_token"


@pytest.mark.parametrize(
    ("debug", "me"),
    [
        ({**VALID, "is_valid": False}, {"id": "fb-9"}),
        ({**VALID, "app_id": "43"}, {"id": "fb-9"}),
        ({**VALID, "expires_at": int(time.time()) - 5}, {"id": "fb-9"}),
        ({**VALID, "user_id": None}, {"id": "fb-9"}),
        (VALID, {"id": "fb-other"}),
        (VALID, ["not", "a", "dict"]),
    ],
)
async def test_facebook_rejects(debug: dict[str, Any], me: Any) -> None:
    fb = FacebookProvider("42", "s3cret", "v27.0", graph(debug, me, []))
    with pytest.raises(ProviderError):
        await fb.verify("EAAB" + "t" * 40, NONCE)


async def test_facebook_limited_login() -> None:
    fb = FacebookProvider("42", "s3cret", "v27.0", jwks_transport([]))
    claims = {"iss": "https://www.facebook.com", "aud": "42", "sub": "fb-ios", "nonce": NONCE}
    ident = await fb.verify(id_token(**claims), NONCE)
    assert (ident.subject, ident.email_verified) == ("fb-ios", False)
    with pytest.raises(ProviderError):
        await fb.verify(id_token(**{**claims, "aud": "99"}), NONCE)

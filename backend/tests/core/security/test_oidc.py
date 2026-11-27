"""Generic OIDC client: PKCE, discovery checks and caching, multi-audience ``azp``."""

from __future__ import annotations

import base64
import hashlib
import time
from typing import Any

import httpx
import pytest

from app.core.security.jwks import IdpUnavailableError, InvalidTokenError
from app.core.security.oidc import OidcClient, pkce_pair
from tests.support.idp import CLIENT_ID, ISSUER, FakeIdp
from tests.support.oidc import id_token

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("app_redis")]


def discovery_client(body: Any, status: int = 200, calls: list[str] | None = None) -> OidcClient:
    def handler(request: httpx.Request) -> httpx.Response:
        (calls if calls is not None else []).append(request.url.path)
        return httpx.Response(status, json=body)

    return OidcClient(ISSUER, CLIENT_ID, "s", transport=httpx.MockTransport(handler))


def test_pkce_challenge_is_s256_of_verifier() -> None:
    verifier, challenge = pkce_pair()
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert (challenge, len(verifier) >= 43) == (digest.decode(), True)
    assert pkce_pair()[0] != verifier


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"issuer": ISSUER}, 200),
        ({"issuer": "https://other.example", "authorization_endpoint": "a",
          "token_endpoint": "t", "jwks_uri": "j"}, 200),
        ({}, 404),
        ([], 200),
    ],
)  # fmt: skip
async def test_bad_discovery_is_unavailable(body: Any, status: int) -> None:
    with pytest.raises(IdpUnavailableError):
        await discovery_client(body, status).discover()


async def test_discovery_is_cached() -> None:
    calls: list[str] = []
    idp = FakeIdp()
    first = await idp.client.discover()
    cached = await discovery_client({}, 500, calls).discover()  # same issuer → Redis copy
    assert (cached, calls) == (first, [])


async def test_multi_audience_token_needs_matching_azp() -> None:
    idp = FakeIdp()
    claims: dict[str, Any] = {"iss": ISSUER, "sub": "s", "nonce": "n", "aud": [CLIENT_ID, "other"]}
    with pytest.raises(InvalidTokenError):
        await idp.client.verify(id_token(**claims, azp="other"), nonce="n", now=time.time())
    ok = await idp.client.verify(id_token(**claims, azp=CLIENT_ID), nonce="n", now=time.time())
    assert ok["azp"] == CLIENT_ID

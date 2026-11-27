"""Generic OIDC authorisation-code client with PKCE, ``state`` and ``nonce`` (R-07, 05 §C.12).

Discovery is cached in Redis for an hour; ID tokens are verified against the IdP's JWKS through
the shared cache in ``core/security/jwks``. The client authenticates at the token endpoint with
``client_secret_post``. Failures surface as ``InvalidTokenError`` or ``IdpUnavailableError``.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from redis.exceptions import RedisError

from app.core.redis import get_redis
from app.core.security.jwks import (
    IdpUnavailableError,
    InvalidTokenError,
    JwksCache,
    request_json,
    verify_id_token,
)

DISCOVERY_TTL_S = 3600
SCOPE = "openid email profile"


@dataclass(frozen=True)
class Discovery:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str


def pkce_pair() -> tuple[str, str]:
    """``(code_verifier, S256 code_challenge)``."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _discovery(body: Any, issuer: str) -> Discovery:
    fields = ("issuer", "authorization_endpoint", "token_endpoint", "jwks_uri")
    if not isinstance(body, dict) or not all(isinstance(body.get(f), str) for f in fields):
        raise IdpUnavailableError("discovery document is incomplete")
    if body["issuer"] != issuer:  # OIDC Discovery §4.3: must match exactly
        raise IdpUnavailableError("discovery issuer mismatch")
    return Discovery(*(body[f] for f in fields))


class OidcClient:
    def __init__(
        self,
        issuer: str,
        client_id: str,
        client_secret: str,
        *,
        breaker: str = "staff_oidc",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.issuer, self.client_id, self.client_secret = issuer, client_id, client_secret
        self.breaker, self.transport = breaker, transport
        self.cache_key = f"oidc:discovery:{hashlib.sha256(issuer.encode()).hexdigest()[:16]}"

    async def discover(self) -> Discovery:
        with contextlib.suppress(RedisError, OSError, ValueError):
            raw = await get_redis().get(self.cache_key)
            if raw:
                return _discovery(json.loads(raw), self.issuer)
        url = f"{self.issuer.rstrip('/')}/.well-known/openid-configuration"
        reply = await request_json(self.breaker, "GET", url, transport=self.transport)
        if reply.status != 200:
            raise IdpUnavailableError("discovery failed")
        found = _discovery(reply.body, self.issuer)
        with contextlib.suppress(RedisError, OSError):
            await get_redis().set(self.cache_key, json.dumps(reply.body), ex=DISCOVERY_TTL_S)
        return found

    def authorize_url(
        self, found: Discovery, *, redirect_uri: str, state: str, nonce: str, challenge: str
    ) -> str:
        query = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{found.authorization_endpoint}?{urlencode(query)}"

    async def exchange(self, code: str, *, redirect_uri: str, code_verifier: str) -> str:
        """Trade the code for tokens; return the ID token. Other tokens are discarded."""
        found = await self.discover()
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code_verifier": code_verifier,
        }
        reply = await request_json(
            self.breaker, "POST", found.token_endpoint, data=form, transport=self.transport
        )
        token = reply.body.get("id_token") if isinstance(reply.body, dict) else None
        if reply.status != 200 or not isinstance(token, str):
            raise InvalidTokenError("token exchange")
        return token

    async def verify(self, id_token: str, *, nonce: str, now: float) -> dict[str, Any]:
        found = await self.discover()
        keys = JwksCache(self.breaker, found.jwks_uri, self.transport)
        claims = await verify_id_token(
            id_token,
            keys,
            issuers=frozenset({found.issuer}),
            audiences=[self.client_id],
            nonce=nonce,
            now=now,
        )
        aud = claims["aud"]
        if isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != self.client_id:
            raise InvalidTokenError("azp")
        return claims

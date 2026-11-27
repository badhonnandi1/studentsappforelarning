"""ID-token verification against an IdP's JWKS, shared by social sign-in and staff SSO.

Keys are cached in Redis by ``kid`` for the ``Cache-Control`` max-age (clamped 5 min–24 h). An
unknown ``kid`` triggers one refetch, at most once per 30 s per URL, so random ``kid`` values
cannot turn into a stream of requests to the IdP. Calls go through a circuit breaker; callers map
``InvalidTokenError`` and ``IdpUnavailableError`` to their own API errors.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
import structlog
from redis.exceptions import RedisError

from app.core.http_client import make_http_client
from app.core.redis import get_redis
from app.core.resilience import CircuitBreaker, CircuitOpenError

log = structlog.get_logger(__name__)
TIMEOUT_S = 3.0
DEFAULT_TTL_S, MIN_TTL_S, MAX_TTL_S = 3600, 300, 86_400
REFETCH_GUARD_S, IAT_SKEW_S = 30, 60
_MAX_AGE = re.compile(r"max-age=(\d+)")


class InvalidTokenError(Exception):
    """The token (or the IdP's answer about it) is not acceptable. Carries no token text."""


class IdpUnavailableError(Exception):
    """The IdP could not be reached, answered 5xx, or its breaker is open."""


@dataclass(frozen=True)
class Reply:
    status: int
    body: Any
    headers: httpx.Headers


async def request_json(
    breaker: str,
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Reply:
    """Only transport errors and 5xx count as breaker failures; a 4xx comes back as a ``Reply``."""

    async def call() -> Reply:
        async with make_http_client(timeout_s=TIMEOUT_S, transport=transport) as client:
            response = await client.request(method, url, params=params, data=data)
        if response.status_code >= 500:
            raise httpx.HTTPStatusError("idp error", request=response.request, response=response)
        try:
            body = response.json()
        except ValueError:
            body = None
        return Reply(response.status_code, body, response.headers)

    try:
        return await CircuitBreaker(breaker, get_redis()).call(call)
    except (httpx.HTTPError, CircuitOpenError, RedisError, OSError) as exc:
        log.warning("idp_unavailable", breaker=breaker, error=type(exc).__name__)
        raise IdpUnavailableError(breaker) from exc


def _ttl(cache_control: str | None) -> int:
    match = _MAX_AGE.search(cache_control or "")
    ttl = int(match.group(1)) if match else DEFAULT_TTL_S
    return max(MIN_TTL_S, min(MAX_TTL_S, ttl))


def _find(keys: dict[str, Any] | None, kid: str) -> dict[str, Any] | None:
    for key in (keys or {}).get("keys", []):
        if isinstance(key, dict) and key.get("kid") == kid:
            return key
    return None


class JwksCache:
    def __init__(self, breaker: str, url: str, transport: httpx.AsyncBaseTransport | None = None):
        self.breaker, self.url, self.transport = breaker, url, transport
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        self.key, self.guard = f"jwks:{digest}", f"jwks:{digest}:refetch"

    async def _fetch(self) -> dict[str, Any]:
        reply = await request_json(self.breaker, "GET", self.url, transport=self.transport)
        if reply.status != 200 or not isinstance(reply.body, dict) or "keys" not in reply.body:
            raise InvalidTokenError("keys")
        ttl = _ttl(reply.headers.get("cache-control"))
        with contextlib.suppress(RedisError, OSError):  # the next request fetches again
            await get_redis().set(self.key, json.dumps(reply.body), ex=ttl)
            await get_redis().set(self.guard, "1", ex=REFETCH_GUARD_S)
        return reply.body

    async def _cached(self) -> dict[str, Any] | None:
        try:
            raw = await get_redis().get(self.key)
        except (RedisError, OSError):
            return None
        return json.loads(raw) if raw else None

    async def _may_refetch(self) -> bool:
        try:
            return bool(await get_redis().set(self.guard, "1", nx=True, ex=REFETCH_GUARD_S))
        except (RedisError, OSError):
            return True

    async def signing_key(self, kid: str) -> Any:
        keys = await self._cached()
        found = _find(keys, kid)
        if found is None and (keys is None or await self._may_refetch()):
            found = _find(await self._fetch(), kid)
        if found is None:
            raise InvalidTokenError("kid")
        try:
            return jwt.PyJWK(found).key
        except (jwt.PyJWKError, jwt.InvalidKeyError) as exc:
            raise InvalidTokenError("jwk") from exc


async def verify_id_token(
    token: str,
    jwks: JwksCache,
    *,
    issuers: frozenset[str],
    audiences: list[str],
    nonce: str,
    now: float,
) -> dict[str, Any]:
    """RS256 against the IdP's keys; ``iss``, ``aud``, ``exp``, ``iat`` (≤ 60 s ahead),
    ``sub`` and ``nonce`` (constant-time) all checked."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("header") from exc
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise InvalidTokenError("alg")
    key = await jwks.signing_key(header["kid"])
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audiences,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("claims") from exc
    if claims["iss"] not in issuers or float(claims["iat"]) > now + IAT_SKEW_S:
        raise InvalidTokenError("iss")
    if not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
        raise InvalidTokenError("nonce")
    return claims

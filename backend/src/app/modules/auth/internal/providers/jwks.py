"""JWKS keys by ``kid``, cached in Redis for the ``Cache-Control`` max-age (05 §C.5).

An unknown ``kid`` triggers one refetch, at most once per 30 s per URL, so random ``kid``
values cannot turn into a stream of requests to the provider.
"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import re
from typing import Any

import httpx
import jwt
from redis.exceptions import RedisError

from app.core.redis import get_redis
from app.modules.auth.internal.providers.base import ProviderError, fetch_json

DEFAULT_TTL_S, MIN_TTL_S, MAX_TTL_S = 3600, 300, 86_400
REFETCH_GUARD_S = 30
_MAX_AGE = re.compile(r"max-age=(\d+)")


def _ttl(cache_control: str | None) -> int:
    match = _MAX_AGE.search(cache_control or "")
    ttl = int(match.group(1)) if match else DEFAULT_TTL_S
    return max(MIN_TTL_S, min(MAX_TTL_S, ttl))


class JwksCache:
    def __init__(self, provider: str, url: str, transport: httpx.AsyncBaseTransport | None = None):
        self.provider, self.url, self.transport = provider, url, transport
        digest = hashlib.sha256(url.encode()).hexdigest()[:16]
        self.key, self.guard = f"jwks:{digest}", f"jwks:{digest}:refetch"

    async def _fetch(self) -> dict[str, Any]:
        reply, headers = await fetch_json(self.provider, self.url, transport=self.transport)
        if reply.status != 200 or not isinstance(reply.body, dict) or "keys" not in reply.body:
            raise ProviderError("The provider's keys could not be read")
        ttl = _ttl(headers.get("cache-control"))
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
            raise ProviderError()
        try:
            return jwt.PyJWK(found).key
        except (jwt.PyJWKError, jwt.InvalidKeyError) as exc:
            raise ProviderError() from exc


def _find(keys: dict[str, Any] | None, kid: str) -> dict[str, Any] | None:
    for key in (keys or {}).get("keys", []):
        if isinstance(key, dict) and key.get("kid") == kid:
            return key
    return None


IAT_SKEW_S = 60


async def verify_id_token(
    token: str,
    jwks: JwksCache,
    *,
    issuers: frozenset[str],
    audiences: list[str],
    nonce: str,
    now: float,
) -> dict[str, Any]:
    """RS256 against the provider's keys; ``iss``, ``aud``, ``exp``, ``iat`` (≤ 60 s ahead),
    ``sub`` and ``nonce`` (constant-time) all checked."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise ProviderError() from exc
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ProviderError()
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
        raise ProviderError() from exc
    if claims["iss"] not in issuers or float(claims["iat"]) > now + IAT_SKEW_S:
        raise ProviderError()
    if not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode()):
        raise ProviderError()
    return claims

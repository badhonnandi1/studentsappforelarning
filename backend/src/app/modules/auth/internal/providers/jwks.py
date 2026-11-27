"""Social-provider view of the shared JWKS verifier (``core/security/jwks``): failures become
``401 invalid_provider_token`` or ``503`` with the phone-OTP fallback."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.security import jwks as core
from app.modules.auth.internal.providers.base import ProviderError, breaker, unavailable


class JwksCache(core.JwksCache):
    def __init__(self, provider: str, url: str, transport: httpx.AsyncBaseTransport | None = None):
        super().__init__(breaker(provider), url, transport)
        self.provider = provider

    async def signing_key(self, kid: str) -> Any:
        try:
            return await super().signing_key(kid)
        except core.InvalidTokenError as exc:
            raise ProviderError() from exc
        except core.IdpUnavailableError as exc:
            raise unavailable(self.provider) from exc


async def verify_id_token(
    token: str,
    jwks: JwksCache,
    *,
    issuers: frozenset[str],
    audiences: list[str],
    nonce: str,
    now: float,
) -> dict[str, Any]:
    try:
        return await core.verify_id_token(
            token, jwks, issuers=issuers, audiences=audiences, nonce=nonce, now=now
        )
    except core.InvalidTokenError as exc:
        raise ProviderError() from exc

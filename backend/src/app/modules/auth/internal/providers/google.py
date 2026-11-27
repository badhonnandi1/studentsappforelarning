"""Google ID token verification (05 §C.5): RS256 against Google's JWKS, issuer, audience
among the configured client ids, expiry, ``iat`` skew and the issued nonce."""

from __future__ import annotations

import time

import httpx

from app.modules.auth.internal.providers.base import ProviderError, VerifiedIdentity
from app.modules.auth.internal.providers.jwks import JwksCache, verify_id_token

JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})


class GoogleProvider:
    name = "google"

    def __init__(self, client_ids: list[str], transport: httpx.AsyncBaseTransport | None = None):
        if not client_ids:
            raise ValueError("Google sign-in needs at least one client id")
        self.client_ids = list(client_ids)
        self.jwks = JwksCache(self.name, JWKS_URL, transport)

    async def verify(self, token: str, nonce: str) -> VerifiedIdentity:
        claims = await verify_id_token(
            token, self.jwks, issuers=ISSUERS, audiences=self.client_ids, nonce=nonce,
            now=time.time(),
        )  # fmt: skip
        email = claims.get("email")
        if email is not None and not isinstance(email, str):
            raise ProviderError()
        return VerifiedIdentity(
            provider=self.name,
            subject=str(claims["sub"]),
            email=email.strip().lower() if email else None,
            email_verified=claims.get("email_verified") is True,
            name=claims.get("name") if isinstance(claims.get("name"), str) else None,
        )

"""Social provider contract (05 §C.5): verify a client-obtained token, return who it is."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.errors import UnauthorizedError, UnavailableError
from app.core.security import jwks


@dataclass(frozen=True)
class VerifiedIdentity:
    provider: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


class SocialProvider(Protocol):
    name: str

    async def verify(self, token: str, nonce: str) -> VerifiedIdentity: ...


class ProviderError(UnauthorizedError):
    """The token is not valid for us. Never carries the token or the provider's reply."""

    code = "invalid_provider_token"

    def __init__(self, message: str = "Sign-in with this account failed") -> None:
        super().__init__(message, code=self.code)


def unavailable(provider: str) -> UnavailableError:
    return UnavailableError(
        f"{provider.title()} sign-in is unavailable; use your phone number",
        details={"fallback": "phone_otp"},
    )


async def fetch_json(
    provider: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> jwks.Reply:
    """GET through the provider's circuit breaker; a 4xx is the token's fault."""
    try:
        return await jwks.request_json(
            breaker(provider), "GET", url, params=params, transport=transport
        )
    except jwks.IdpUnavailableError as exc:
        raise unavailable(provider) from exc


def breaker(provider: str) -> str:
    return f"social_{provider}"

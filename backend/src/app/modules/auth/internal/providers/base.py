"""Social provider contract (05 §C.5): verify a client-obtained token, return who it is."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
import structlog
from redis.exceptions import RedisError

from app.core.errors import UnauthorizedError, UnavailableError
from app.core.http_client import make_http_client
from app.core.redis import get_redis
from app.core.resilience import CircuitBreaker, CircuitOpenError

log = structlog.get_logger(__name__)
TIMEOUT_S = 3.0


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


@dataclass(frozen=True)
class Reply:
    status: int
    body: Any


async def fetch_json(
    provider: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[Reply, httpx.Headers]:
    """GET through the provider's circuit breaker. Only transport errors and 5xx count as
    failures; a 4xx is the token's fault and comes back as a ``Reply``."""

    async def call() -> tuple[Reply, httpx.Headers]:
        async with make_http_client(timeout_s=TIMEOUT_S, transport=transport) as client:
            response = await client.get(url, params=params)
        if response.status_code >= 500:
            raise httpx.HTTPStatusError(
                "provider error", request=response.request, response=response
            )
        try:
            body = response.json()
        except ValueError:
            body = None
        return Reply(response.status_code, body), response.headers

    return await guarded(provider, call)


async def guarded[T](provider: str, fn: Callable[[], Awaitable[T]]) -> T:
    try:
        return await CircuitBreaker(f"social_{provider}", get_redis()).call(fn)
    except (httpx.HTTPError, CircuitOpenError, RedisError, OSError) as exc:
        log.warning("social_provider_unavailable", provider=provider, error=type(exc).__name__)
        raise unavailable(provider) from exc

"""Shared outbound HTTPX client factory: explicit timeouts, a fixed user agent, no redirects."""

from __future__ import annotations

import httpx

USER_AGENT = "studyplatform-backend/1"


def make_http_client(
    *, timeout_s: float = 3.0, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_s, connect=min(timeout_s, 2.0)),
        headers={"User-Agent": USER_AGENT},
        follow_redirects=False,
        transport=transport,
    )

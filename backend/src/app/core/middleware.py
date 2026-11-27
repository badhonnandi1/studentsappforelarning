"""Pure-ASGI middleware: security headers, minimum app version header, body size limit."""

from __future__ import annotations

import json
from collections.abc import Callable

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import current_request_id

DEFAULT_BODY_LIMIT = 256 * 1024
BATCH_BODY_LIMIT = 1024 * 1024
BATCH_PATHS = ("/v1/practice/answers:sync", "/v1/events:batch")
BATCH_PREFIXES = ("/v1/ingest/",)

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}
JSON_CSP = "default-src 'none'; frame-ancestors 'none'"
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, min_app_version: Callable[[], str]) -> None:
        self.app = app
        self.min_app_version = min_app_version

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope["path"].startswith(DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if not is_docs:
                    headers.setdefault("Content-Security-Policy", JSON_CSP)
                headers["X-Min-App-Version"] = self.min_app_version()
            await send(message)

        await self.app(scope, receive, send_with_headers)


def body_limit_for(path: str) -> int:
    if path in BATCH_PATHS or path.startswith(BATCH_PREFIXES):
        return BATCH_BODY_LIMIT
    return DEFAULT_BODY_LIMIT


class BodyLimitMiddleware:
    """413 when Content-Length or the streamed body exceeds the limit for the path."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = body_limit_for(scope["path"])
        declared = Headers(scope=scope).get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > limit:
            await _send_413(send)
            return
        received = 0
        rejected = False

        async def limited_receive() -> Message:
            nonlocal received, rejected
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    rejected = True
                    raise _TooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _TooLargeError:
            await _send_413(send)


class _TooLargeError(Exception):
    pass


async def _send_413(send: Send) -> None:
    error = {
        "code": "payload_too_large",
        "message": "Request body too large",
        "request_id": current_request_id(),
    }
    body = json.dumps({"error": error}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})

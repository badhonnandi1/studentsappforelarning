"""Outermost pure-ASGI middleware: request id, trace id, one access log line, last-resort 500.

The access log records the route template, never the raw path or query string, so ids and
phone numbers in URLs stay out of logs.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_OK = re.compile(r"[A-Za-z0-9._-]{1,64}")
_TRACEPARENT = re.compile(r"00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_client_ip: ContextVar[str | None] = ContextVar("client_ip", default=None)
log = structlog.get_logger("app.request")


def current_request_id() -> str | None:
    return _request_id.get()


def current_client_ip() -> str | None:
    """Cloudflare's ``CF-Connecting-IP`` (the edge strips client copies), else the peer."""
    return _client_ip.get()


def _scope_ip(scope: Scope, headers: Headers) -> str | None:
    forwarded = headers.get("cf-connecting-ip", "").strip()
    if forwarded:
        return forwarded
    client = scope.get("client")
    return str(client[0]) if client else None


def _internal_error_body(request_id: str) -> bytes:
    error = {"code": "internal_error", "message": "Internal error", "request_id": request_id}
    return json.dumps({"error": error}).encode()


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        inbound = headers.get(REQUEST_ID_HEADER, "")
        request_id = inbound if _REQUEST_ID_OK.fullmatch(inbound) else uuid.uuid4().hex
        trace = _TRACEPARENT.fullmatch(headers.get("traceparent", ""))
        bound: dict[str, str] = {"request_id": request_id}
        if trace:
            bound["trace_id"] = trace.group(1)
        status_code = 500
        started = False

        async def send_with_id(message: Message) -> None:
            nonlocal status_code, started
            if message["type"] == "http.response.start":
                started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        token = _request_id.set(request_id)
        ip_token = _client_ip.set(_scope_ip(scope, headers))
        begin = time.perf_counter()
        with structlog.contextvars.bound_contextvars(**bound):
            try:
                await self.app(scope, receive, send_with_id)
            except Exception:
                log.exception("unhandled_error")
                if started:
                    raise
                await _send_500(send, request_id)
                status_code = 500
            finally:
                route = getattr(scope.get("route"), "path", "unmatched")
                log.info(
                    "request",
                    method=scope["method"],
                    route=route,
                    status=status_code,
                    ms=round((time.perf_counter() - begin) * 1000, 1),
                )
                _request_id.reset(token)
                _client_ip.reset(ip_token)


async def _send_500(send: Send, request_id: str) -> None:
    body = _internal_error_body(request_id)
    await send(
        {
            "type": "http.response.start",
            "status": 500,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (REQUEST_ID_HEADER.lower().encode(), request_id.encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})

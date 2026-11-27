"""Error hierarchy and handlers producing the 14 §1.5 envelope.

Services raise ``AppError`` subclasses; routers never build error responses themselves.
Unhandled exceptions are turned into 500 ``internal_error`` by the request-context middleware.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import current_request_id


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = dict(details) if details else None
        self.headers = dict(headers) if headers else None


class UnauthorizedError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class GoneError(AppError):
    status_code = status.HTTP_410_GONE
    code = "expired"


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "payload_too_large"


class ValidationAppError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class LockedError(AppError):
    status_code = status.HTTP_423_LOCKED
    code = "locked_exam"


class UpgradeRequiredError(AppError):
    status_code = status.HTTP_426_UPGRADE_REQUIRED
    code = "upgrade_required"


class TooManyRequestsError(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "too_many_requests"

    def __init__(self, message: str, *, retry_after: int, code: str | None = None) -> None:
        super().__init__(message, code=code, headers={"Retry-After": str(max(1, retry_after))})


class UnavailableError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "unavailable"


def envelope(code: str, message: str, details: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = dict(details)
    body["request_id"] = current_request_id()
    return {"error": body}


_HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 401: "unauthorized", 403: "forbidden"}


def add_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = dict(exc.headers or {})
        if isinstance(exc, UnauthorizedError):
            headers.setdefault("WWW-Authenticate", "Bearer")
        return JSONResponse(
            envelope(exc.code, exc.message, exc.details),
            status_code=exc.status_code,
            headers=headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            envelope("validation_error", "Request validation failed", {"fields": fields}),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "bad_request")
        return JSONResponse(
            envelope(code, str(exc.detail)),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )

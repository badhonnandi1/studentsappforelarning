"""structlog setup (JSON in deployed environments, console locally) with PII redaction.

Any key whose name contains a sensitive word is replaced with ``"[redacted]"``, at any depth
of nested dicts and lists. Values are never pattern-scanned here: callers must not put PII in
free-text messages, and ``tests/security`` checks the database for plain-text PII.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, MutableMapping
from typing import Any

import structlog

REDACTED = "[redacted]"
SENSITIVE_KEYS = (
    "phone",
    "email",
    "token",
    "otp",
    "answer_key",
    "password",
    "secret",
    "authorization",
    "cookie",
    "signed_request",
    "code_verifier",
)
_SAFE_SUFFIXES = ("_hash", "_count", "_id")


def is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if lowered.endswith(_SAFE_SUFFIXES):
        return False
    return any(word in lowered for word in SENSITIVE_KEYS)


def _scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: REDACTED if is_sensitive(str(k)) else _scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def redact_pii(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key == "event":
            continue
        event_dict[key] = REDACTED if is_sensitive(key) else _scrub(event_dict[key])
    return event_dict


def configure_logging(*, json: bool, level: str = "INFO") -> None:
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        redact_pii,
    ]
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                renderer,
            ],
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True

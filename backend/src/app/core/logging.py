"""structlog setup (JSON in deployed environments, console locally) with PII redaction.

Any key whose name contains a sensitive word is replaced with ``"[redacted]"``, at any depth
of nested dicts and lists. String values, the event text and rendered tracebacks are also
scanned for Bangladesh mobile numbers and email addresses as a second line of defence; callers
still must not put PII in free text.
"""

from __future__ import annotations

import logging
import re
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
    "appsecret",
    "api_key",
    "private_key",
)
_SAFE_SUFFIXES = ("_hash", "_count", "_id")


def is_sensitive(key: str) -> bool:
    lowered = key.lower()
    if lowered.endswith(_SAFE_SUFFIXES):
        return False
    return any(word in lowered for word in SENSITIVE_KEYS)


# Values, not keys: a phone number or email that reaches a log through free text (an exception
# message, a provider error body) is masked too. Bangladesh mobiles in any common spelling.
_PHONE = re.compile(r"(?<!\d)(?:\+?880|0)1[3-9]\d{8}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def scrub_text(text: str) -> str:
    return _EMAIL.sub(REDACTED, _PHONE.sub(REDACTED, text))


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {k: REDACTED if is_sensitive(str(k)) else _scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def redact_pii(_: Any, __: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        event_dict[key] = REDACTED if is_sensitive(key) else _scrub(event_dict[key])
    return event_dict


def redact_rendered(
    _: Any, __: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """After ``format_exc_info``: mask PII inside the rendered traceback text."""
    if isinstance(event_dict.get("exception"), str):
        event_dict["exception"] = scrub_text(event_dict["exception"])
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
                redact_rendered,
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

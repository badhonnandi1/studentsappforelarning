"""Cursor pagination (14 §1): ``?limit=`` (default 20, max 100) and an opaque ``?cursor=``.

The cursor is base64url JSON of the last row's sort key. A malformed cursor is a 422.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from typing import Annotated, Any

from fastapi import Query
from pydantic import BaseModel

from app.core.errors import ValidationAppError

Limit = Annotated[int, Query(ge=1, le=100)]
DEFAULT_LIMIT = 20


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


def encode_cursor(key: Sequence[Any]) -> str:
    raw = json.dumps(list(key), separators=(",", ":"), default=str).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(cursor: str | None, size: int) -> list[Any] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded.encode()))
    except (ValueError, binascii.Error) as exc:
        raise ValidationAppError("Invalid cursor", details={"cursor": "malformed"}) from exc
    if not isinstance(value, list) or len(value) != size:
        raise ValidationAppError("Invalid cursor", details={"cursor": "malformed"})
    return value

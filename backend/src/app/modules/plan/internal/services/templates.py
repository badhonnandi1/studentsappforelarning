"""Template rendering (``{placeholder}``, Bangla numerals) and SMS segment counting.

Numbers passed as ``int`` are written in Bangla digits for ``bn``; strings are inserted as
they are, so an OTP code stays in ASCII digits (SMS autofill reads ASCII). Segments follow
GSM 03.38: GSM-7 is 160 characters, or 153 per part when concatenated (extension characters
count twice); anything else is UCS-2 at 70, or 67 per part, counted in UTF-16 code units.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plan.internal.repositories import sms as repo
from app.shared.numerals import localise_digits

PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
MAX_TEMPLATE_SEGMENTS = 2  # 01 §3.4: SMS bodies stay within 2 Unicode segments
MAX_SEGMENTS = 10
GSM7_BASIC = frozenset(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENSION = frozenset("^{}\\[~]|€\f")
CACHE_TTL_S = 60.0
_cache: dict[tuple[str, str, str], tuple[float, str]] = {}


def render(body: str, params: Mapping[str, object], lang: str) -> str:
    def value(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            raise ValueError(f"template parameter {name!r} is missing")
        param = params[name]
        if isinstance(param, int) and not isinstance(param, bool):
            return localise_digits(param, lang)
        return str(param)

    return PLACEHOLDER.sub(value, body)


def is_gsm7(text: str) -> bool:
    return all(c in GSM7_BASIC or c in GSM7_EXTENSION for c in text)


def segments(text: str) -> int:
    if not text:
        return 1
    if is_gsm7(text):
        septets = sum(2 if c in GSM7_EXTENSION else 1 for c in text)
        return 1 if septets <= 160 else math.ceil(septets / 153)
    units = len(text.encode("utf-16-le")) // 2
    return 1 if units <= 70 else math.ceil(units / 67)


async def load(session: AsyncSession, code: str, lang: str, channel: str = "sms") -> str:
    key = (code, lang, channel)
    cached = _cache.get(key)
    if cached is not None and cached[0] > time.monotonic():
        return cached[1]
    body = await repo.get_template(session, code, lang, channel)
    if body is None:
        raise LookupError(f"no {channel} template {code!r} in {lang!r}")
    _cache[key] = (time.monotonic() + CACHE_TTL_S, body)
    return body


def clear_cache() -> None:
    _cache.clear()

"""One rule for Bangladesh mobile numbers (starter copy).

Input may be ``01…``, ``8801…``, ``+880 1…`` or use Bangla digits; storage is always
``+8801XXXXXXXXX`` (operator digit 3–9).
"""

from __future__ import annotations

import re

MOBILE = re.compile(r"^(?:\+?88)?0?(1[3-9][0-9]{8})$")
BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
E164 = re.compile(r"^\+8801[3-9][0-9]{8}$")


def normalize_bd_phone(value: str | None) -> str | None:
    match = MOBILE.match(re.sub(r"[\s\-().]", "", (value or "").translate(BANGLA_DIGITS)))
    return f"+880{match.group(1)}" if match else None


def local_bd_phone(stored: str) -> str:
    return f"0{stored[4:]}"


def mask_bd_phone(stored: str) -> str:
    """``+8801712345678`` -> ``01*******78`` for display in support tools and SMS logs."""
    local = local_bd_phone(stored)
    return f"{local[:2]}{'*' * (len(local) - 4)}{local[-2:]}"

"""One rule for Bangladesh mobile numbers: forms take 01…, 8801…, +880 1… or Bangla digits; storage is +8801XXXXXXXXX."""

import re

MOBILE = re.compile(r"^(?:\+?88)?0?(1[3-9][0-9]{8})$")
BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalize_bd_phone(value: str | None) -> str | None:
    match = MOBILE.match(re.sub(r"[\s\-().]", "", (value or "").translate(BANGLA_DIGITS)))
    return f"+880{match.group(1)}" if match else None


def local_bd_phone(stored: str) -> str:
    return f"0{stored[4:]}"

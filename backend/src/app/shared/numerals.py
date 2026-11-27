"""Bangla numerals for templates and display."""

from __future__ import annotations

TO_BANGLA = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def bangla_digits(value: object) -> str:
    return str(value).translate(TO_BANGLA)


def ascii_digits(value: str) -> str:
    return value.translate(TO_ASCII)


def localise_digits(value: object, lang: str) -> str:
    return bangla_digits(value) if lang == "bn" else str(value)

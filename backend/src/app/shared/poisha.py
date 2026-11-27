"""Money as integer poisha (100 poisha = 1 taka). Decimal appears only at provider edges."""

from __future__ import annotations

from decimal import Decimal

from app.shared.money import group_lakh, quantize
from app.shared.numerals import localise_digits
from app.shared.types import Poisha

TAKA_SIGN = "৳"


def format_poisha(amount: int, lang: str = "bn") -> str:
    """``24900`` -> ``৳২৪৯.০০`` (bn) or ``৳249.00`` (en), with lakh grouping."""
    text = group_lakh(Decimal(amount) / 100)
    sign = ""
    if text.startswith("-"):
        sign, text = "-", text[1:]
    return f"{sign}{TAKA_SIGN}{localise_digits(text, lang)}"


def parse_provider_amount(value: str) -> Poisha:
    """A provider's decimal string (``"249.00"``) to poisha, rounding half up once."""
    return Poisha(int(quantize(value) * 100))


def to_provider_amount(amount: int) -> str:
    return f"{Decimal(amount) / 100:.2f}"

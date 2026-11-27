from datetime import UTC, date, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from app.shared import bangla_text as bt
from app.shared.bd_phone import local_bd_phone, mask_bd_phone, normalize_bd_phone
from app.shared.dhaka_date import (
    age_on,
    dhaka_date,
    dhaka_day_range,
    dhaka_month_key,
    dhaka_today,
    dhaka_week_key,
)
from app.shared.numerals import ascii_digits, bangla_digits, localise_digits
from app.shared.poisha import format_poisha, parse_provider_amount, to_provider_amount
from app.shared.types import BdPhone

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "raw",
    ["01712345678", "+8801712345678", "8801712345678", "+880 1712-345678", "০১৭১২৩৪৫৬৭৮"],
)
def test_phone_variants_normalise(raw: str) -> None:
    assert normalize_bd_phone(raw) == "+8801712345678"


@pytest.mark.parametrize("raw", ["01212345678", "0171234567", "+11712345678", "", None])
def test_invalid_phones(raw: str | None) -> None:
    assert normalize_bd_phone(raw) is None


def test_phone_display_helpers_and_type() -> None:
    assert local_bd_phone("+8801712345678") == "01712345678"
    assert mask_bd_phone("+8801712345678") == "01*******78"
    assert TypeAdapter(BdPhone).validate_python("01812345678") == "+8801812345678"
    with pytest.raises(ValidationError):
        TypeAdapter(BdPhone).validate_python("123")


def test_dhaka_date_boundary() -> None:
    assert dhaka_date(datetime(2026, 3, 1, 17, 59, 59, tzinfo=UTC)) == date(2026, 3, 1)
    assert dhaka_date(datetime(2026, 3, 1, 18, 0, 0, tzinfo=UTC)) == date(2026, 3, 2)
    assert dhaka_today(datetime(2026, 3, 1, 18, tzinfo=UTC)) == date(2026, 3, 2)
    with pytest.raises(ValueError, match="aware"):
        dhaka_date(datetime(2026, 3, 1))
    start, end = dhaka_day_range(date(2026, 3, 1))
    assert (end - start).days == 1
    assert start.utcoffset() is not None


@pytest.mark.parametrize(
    ("day", "key"),
    [
        (date(2026, 1, 10), "2026-01-10"),  # Saturday
        (date(2026, 1, 16), "2026-01-10"),  # Friday
        (date(2026, 1, 17), "2026-01-17"),  # next Saturday
    ],
)
def test_saturday_week_keys(day: date, key: str) -> None:
    assert dhaka_week_key(day) == key


def test_month_key_and_age() -> None:
    assert dhaka_month_key(date(2026, 2, 9)) == "2026-02"
    assert age_on(date(2013, 5, 1), date(2026, 4, 30)) == 12
    assert age_on(date(2013, 5, 1), date(2026, 5, 1)) == 13
    assert age_on(date(2012, 2, 29), date(2025, 2, 28)) == 12
    assert age_on(date(2012, 2, 29), date(2025, 3, 1)) == 13


def test_numerals_and_poisha() -> None:
    assert bangla_digits(2026) == "২০২৬"
    assert ascii_digits("২০২৬") == "2026"
    assert localise_digits(5, "en") == "5"
    assert format_poisha(24900, "bn") == "৳২৪৯.০০"
    assert format_poisha(24900, "en") == "৳249.00"
    assert format_poisha(12345678900, "en") == "৳12,34,56,789.00"
    assert format_poisha(-500, "en") == "-৳5.00"
    assert parse_provider_amount("249.005") == 24901
    assert to_provider_amount(24900) == "249.00"


def test_bangla_normalise_nfc_zero_width_digits() -> None:
    assert bt.normalise("  গণিত​ ১০  ") == "গণিত 10"
    assert bt.normalise("Physics‌Test") == "physicstest"
    assert bt.is_bangla("গণিত")
    assert not bt.is_bangla("math")


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("শিক্ষা", "সিক্ষা"),  # শ/স
        ("ভাষা", "ভাসা"),  # ষ/স
        ("নীতি", "নিতি"),  # ী/ি
        ("মূল", "মুল"),  # ূ/ু
        ("কারণ", "কারন"),  # ণ/ন
        ("চাঁদ", "চাদ"),  # chandrabindu dropped
    ],
)
def test_bangla_folding_pairs(a: str, b: str) -> None:
    assert bt.fold(a) == bt.fold(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("nioton er sutro", "niooton er shutro"),
        ("Bhalo", "balo"),
        ("phiziks", "fiziks"),
        ("zibon", "jibon"),
        ("f@k3", "fake"),
    ],
)
def test_banglish_folding(a: str, b: str) -> None:
    assert bt.fold(a) == bt.fold(b)


def test_tokens() -> None:
    assert bt.tokens("Nioton-er  sutro!") == ["nioton", "er", "sutro"]

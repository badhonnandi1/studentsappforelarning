"""Text normalisation and folding for Bangla, English and Banglish (romanised Bangla).

``normalise`` makes text comparable without losing meaning (NFC, no zero-width characters,
ASCII digits, lower case, single spaces). ``fold`` goes further for matching: it merges letters
that learners commonly swap (ি/ী, ু/ূ, ণ/ন, শ/ষ/স, …) and spelling variants of romanised Bangla,
so "nioton er sutro" and "niooton er shutro" fold to the same string. Used by moderation (COM)
and later by search.
"""

from __future__ import annotations

import re
import unicodedata

ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
BANGLA_TO_ASCII_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_SPACES = re.compile(r"\s+")

# Bangla letters merged by ``fold`` (each key becomes its value).
BANGLA_FOLDS = str.maketrans(
    {
        "ী": "ি",  # dirgho i -> hrosso i
        "ূ": "ু",  # dirgho u -> hrosso u
        "ণ": "ন",  # murdhonno no -> dontto no
        "শ": "স",
        "ষ": "স",
        "ৎ": "ত",
        "ঙ": "ং",
        "ঈ": "ই",
        "ঊ": "উ",
        "ঁ": None,  # chandrabindu
        "়": None,  # nukta (NFC keeps য় ড় ঢ় decomposed); য় folds into য
    }
)

# Romanised variants, applied in order after lower-casing.
BANGLISH_RULES: tuple[tuple[str, str], ...] = (
    ("sh", "s"),
    ("ph", "f"),
    ("kh", "k"),
    ("gh", "g"),
    ("ch", "c"),
    ("jh", "j"),
    ("th", "t"),
    ("dh", "d"),
    ("bh", "b"),
    ("ou", "u"),
    ("z", "j"),
    ("q", "k"),
    ("w", "o"),
    ("y", "i"),
)
# Look-alike characters used to dodge filters ("f@k3" -> "fake").
LEET = str.maketrans(
    {"@": "a", "$": "s", "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"}
)
_REPEATS = re.compile(r"(.)\1+")
_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(ZERO_WIDTH)
    text = text.translate(BANGLA_TO_ASCII_DIGITS).lower()
    return _SPACES.sub(" ", text).strip()


def is_bangla(text: str) -> bool:
    return any("ঀ" <= ch <= "৿" for ch in text)


def fold_bangla(text: str) -> str:
    return normalise(text).translate(BANGLA_FOLDS)


def fold_banglish(text: str) -> str:
    text = normalise(text).translate(LEET)
    text = _REPEATS.sub(r"\1", _NON_WORD.sub(" ", text))  # "niooton" -> "nioton"
    for old, new in BANGLISH_RULES:
        text = text.replace(old, new)
    text = _REPEATS.sub(r"\1", text)
    return _SPACES.sub(" ", text).strip()


def fold(text: str) -> str:
    """Fold for matching: Bangla letters and Latin spellings both collapse to one form."""
    return fold_banglish(fold_bangla(text))


def tokens(text: str) -> list[str]:
    return fold(text).split()

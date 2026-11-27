import pytest

from app.shared import bangla_text as bt

pytestmark = pytest.mark.unit


def test_normalise_nfc_zero_width_digits_case_spaces() -> None:
    decomposed = "য়"  # য + nukta
    assert bt.normalise(decomposed) == bt.normalise("য়")
    assert bt.normalise("নি​য়‌ম") == "নিয়ম"
    assert bt.normalise("ক্লাস ১০") == "ক্লাস 10"
    assert bt.normalise("  Hello\t\nWORLD  ") == "hello world"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("নীতি", "নিতি"),
        ("মূল", "মুল"),
        ("কারণ", "কারন"),
        ("শিক্ষা", "সিক্ষা"),
        ("ভাষা", "ভাসা"),
        ("চাঁদ", "চাদ"),
        ("nioton er sutro", "niooton er shutro"),
        ("khub bhalo", "kub balo"),
        ("zor", "jor"),
    ],
)
def test_fold_merges_common_variants(a: str, b: str) -> None:
    assert bt.fold(a) == bt.fold(b)


def test_fold_keeps_different_words_apart() -> None:
    assert bt.fold("কলম") != bt.fold("কলা")
    assert bt.fold("pani") != bt.fold("pana")


def test_leet_and_punctuation() -> None:
    assert bt.fold("f@k3!!") == bt.fold("fake")
    assert bt.fold_latin("$c@m") == "scam"
    assert bt.fold_latin("baaaad, word") == "bad word"


def test_fold_latin_keeps_double_letters() -> None:
    assert bt.fold_latin("ass") != bt.fold_latin("as")
    assert bt.fold_latin("class") == "class"


def test_bangla_words_stay_whole() -> None:
    assert bt.tokens("সয়তান, শিক্ষা!") == ["সযতান", "সিক্সা"]
    assert bt.fold("ক্লাস।") == "ক্লাস"  # the danda goes


def test_is_bangla_and_tokens() -> None:
    assert bt.is_bangla("আমি ok")
    assert not bt.is_bangla("ami ok")
    assert bt.tokens("Nioton  er  SUTRO") == ["nioton", "er", "sutro"]

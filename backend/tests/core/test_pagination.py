import pytest

from app.core.errors import ValidationAppError
from app.core.pagination import Page, decode_cursor, encode_cursor

pytestmark = pytest.mark.unit


def test_cursor_round_trip() -> None:
    cursor = encode_cursor(["2026-01-01T00:00:00+00:00", "abc"])
    assert "=" not in cursor
    assert decode_cursor(cursor, 2) == ["2026-01-01T00:00:00+00:00", "abc"]
    assert decode_cursor(None, 2) is None
    assert decode_cursor("", 2) is None


@pytest.mark.parametrize("bad", ["%%%", encode_cursor(["only-one"]), "e30"])
def test_malformed_cursor(bad: str) -> None:
    with pytest.raises(ValidationAppError):
        decode_cursor(bad, 2)


def test_page_model() -> None:
    page = Page[int](items=[1, 2])
    assert page.model_dump() == {"items": [1, 2], "next_cursor": None}

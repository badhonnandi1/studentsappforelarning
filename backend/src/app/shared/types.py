from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, PlainSerializer

from app.shared.bd_phone import normalize_bd_phone
from app.shared.money import quantize


def _bd_phone(value: str) -> str:
    phone = normalize_bd_phone(value)
    if phone is None:
        raise ValueError("not a Bangladesh mobile number")
    return phone


def _money(value: object) -> Decimal:
    # pydantic turns only ValueError into a 422; money.py raises TypeError for floats
    if not isinstance(value, Decimal | int | str) or isinstance(value, bool):
        raise ValueError("amount must be a decimal string, never a float")
    return quantize(value)


def _blank_to_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


BdPhone = Annotated[str, AfterValidator(_bd_phone)]
OptionalBdPhone = Annotated[BdPhone | None, BeforeValidator(_blank_to_none)]
Money = Annotated[Decimal, BeforeValidator(_money), PlainSerializer(str, return_type=str)]

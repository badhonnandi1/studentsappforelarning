from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.shared.types import BdPhone, Money


class Payment(BaseModel):
    amount: Money
    phone: BdPhone


def test_money_rounds_once_and_serializes_as_string() -> None:
    payment = Payment(amount="10.005", phone="01711223344")
    assert payment.amount == Decimal("10.01")
    assert payment.model_dump(mode="json") == {"amount": "10.01", "phone": "+8801711223344"}


def test_money_refuses_a_float() -> None:
    with pytest.raises(ValidationError):
        Payment.model_validate_json('{"amount": 10.5, "phone": "01711223344"}')


def test_phone_refuses_a_landline() -> None:
    with pytest.raises(ValidationError):
        Payment(amount="1", phone="029876543")

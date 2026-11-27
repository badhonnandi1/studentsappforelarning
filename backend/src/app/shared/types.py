"""Shared annotated types for schemas and services."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, NewType

from pydantic import AfterValidator

from app.shared.bd_phone import normalize_bd_phone

Poisha = NewType("Poisha", int)
Lang = Literal["bn", "en"]
DhakaDate = date


def _bd_phone(value: str) -> str:
    normalised = normalize_bd_phone(value)
    if normalised is None:
        raise ValueError("not a Bangladesh mobile number")
    return normalised


BdPhone = Annotated[str, AfterValidator(_bd_phone)]

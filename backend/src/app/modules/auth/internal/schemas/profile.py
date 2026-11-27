"""Profile, photo and reference-list models (05 §D, rules in §C.4)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.auth.internal.schemas.auth import In

# 6–12 are school classes; the API speaks ``admission`` and ``job``, stored as 13 and 14.
ClassLevel = Annotated[int, Field(ge=6, le=12)] | Literal["admission", "job"]
GroupCode = Literal["science", "business", "humanities", "general"]
CLASS_WORDS: dict[str, int] = {"admission": 13, "job": 14}


class ProfileIn(In):
    class_level: ClassLevel
    group_code: GroupCode | None = None
    version_lang: Literal["bn", "en"]
    curriculum: Literal["general", "madrasah", "technical"]
    institution_id: uuid.UUID | None = None
    district_id: int | None = Field(default=None, ge=1, le=32767)
    upazila_id: int | None = Field(default=None, ge=1)
    board_code: str | None = Field(default=None, pattern=r"^[a-z_]{2,20}$")
    exam_year: int | None = None
    date_of_birth: date | None = None


class ProfileOut(BaseModel):
    class_level: ClassLevel | None
    group_code: GroupCode | None
    version_lang: Literal["bn", "en"] | None
    curriculum: Literal["general", "madrasah", "technical"] | None
    institution_id: uuid.UUID | None
    district_id: int | None
    upazila_id: int | None
    board_code: str | None
    exam_year: int | None
    date_of_birth: date | None
    photo_status: Literal["none", "pending", "approved", "rejected"]
    needs_consent: bool


class PhotoIn(In):
    upload_key: str = Field(min_length=10, max_length=200)


class PhotoOut(BaseModel):
    photo_status: Literal["pending"] = "pending"


class UpazilaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name_bn: str
    name_en: str


class DistrictOut(BaseModel):
    id: int
    division: str
    name_bn: str
    name_en: str
    upazilas: list[UpazilaOut]


class DistrictsOut(BaseModel):
    items: list[DistrictOut]


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name_bn: str
    name_en: str
    kind: str
    district_id: int

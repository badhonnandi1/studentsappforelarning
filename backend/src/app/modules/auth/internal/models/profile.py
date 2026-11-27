"""``identity.profiles``, ``districts``, ``upazilas`` and ``institutions`` (01 §4.2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, updated_at, uuid_pk

GROUPS = ("science", "business", "humanities", "general")
CURRICULA = ("general", "madrasah", "technical")
PHOTO_STATUSES = ("none", "pending", "approved", "rejected")
REPLY_LANGS = ("auto", "bn", "en", "banglish")
INSTITUTION_KINDS = (
    "school", "college", "school_college", "madrasah", "technical", "university", "coaching",
    "other",
)  # fmt: skip
SOURCES = ("seed", "user_suggested", "ops")


class District(Base):
    __tablename__ = "districts"
    __table_args__ = ({"schema": "identity"},)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    division: Mapped[str] = mapped_column(Text, nullable=False)
    name_bn: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False, unique=True)


class Upazila(Base):
    __tablename__ = "upazilas"
    __table_args__ = (UniqueConstraint("district_id", "name_en"), {"schema": "identity"})

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    district_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("identity.districts.id"), nullable=False
    )
    name_bn: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)


class Institution(Base):
    __tablename__ = "institutions"
    __table_args__ = (
        check_in("kind", INSTITUTION_KINDS),
        check_in("source", SOURCES),
        Index(
            "uq_institutions_eiin", "eiin", unique=True, postgresql_where=text("eiin IS NOT NULL")
        ),
        Index("ix_institutions_district_id", "district_id"),
        Index(
            "ix_institutions_name_bn_trgm",
            "name_bn",
            postgresql_using="gin",
            postgresql_ops={"name_bn": "gin_trgm_ops"},
        ),
        Index(
            "ix_institutions_name_en_trgm",
            "name_en",
            postgresql_using="gin",
            postgresql_ops={"name_en": "gin_trgm_ops"},
        ),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    eiin: Mapped[str | None] = mapped_column(Text)
    name_bn: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    district_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("identity.districts.id"), nullable=False
    )
    upazila_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("identity.upazilas.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    source: Mapped[str] = mapped_column(Text, nullable=False, server_default="seed")


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint("class_level BETWEEN 6 AND 14", name="class_level"),
        check_in("group_code", GROUPS),
        check_in("version_lang", ("bn", "en")),
        check_in("curriculum", CURRICULA),
        CheckConstraint("exam_year BETWEEN 2025 AND 2040", name="exam_year"),
        check_in("photo_status", PHOTO_STATUSES),
        check_in("reply_lang_pref", REPLY_LANGS),
        Index("ix_profiles_institution_id", "institution_id"),
        Index("ix_profiles_district_id", "district_id"),
        {"schema": "identity"},
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), primary_key=True
    )
    class_level: Mapped[int | None] = mapped_column(SmallInteger)
    group_code: Mapped[str | None] = mapped_column(Text)
    version_lang: Mapped[str | None] = mapped_column(Text)
    curriculum: Mapped[str | None] = mapped_column(Text)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.institutions.id")
    )
    district_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("identity.districts.id")
    )
    upazila_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("identity.upazilas.id"))
    board_code: Mapped[str | None] = mapped_column(Text)
    exam_year: Mapped[int | None] = mapped_column(SmallInteger)
    photo_key: Mapped[str | None] = mapped_column(Text)
    photo_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    reply_lang_pref: Mapped[str] = mapped_column(Text, nullable=False, server_default="auto")
    updated_at: Mapped[datetime] = updated_at()

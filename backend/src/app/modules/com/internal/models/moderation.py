"""``community.moderation_terms``, ``moderation_decisions``, ``content_reports`` and
``user_restrictions`` (01 §3.3; CHECK lists per ``b01_12``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, tstz, uuid_pk

TERM_LANGS = ("bn", "en", "banglish")
CATEGORIES = ("profanity", "sexual", "hate", "self_harm", "contact_info", "spam")
CONTEXTS = (
    "display_name", "profile_photo", "error_report", "ticket", "tutor_input", "tutor_output",
    "post", "group_message", "content_report",
)  # fmt: skip
VERDICTS = ("flag", "block")
REPORT_TARGETS = (
    "user", "display_name", "profile_photo", "post", "thread", "group_message",
    "tutor_message", "other",
)  # fmt: skip
REPORT_REASONS = ("abuse", "spam", "sexual", "self_harm", "privacy", "cheating", "other")
REPORT_STATUSES = ("open", "actioned", "dismissed")
RESTRICTION_KINDS = ("mute", "ban")
SCOPES = ("global", "community", "tutor", "display_name", "profile")
S = {"schema": "community"}


def _user_fk(*, nullable: bool) -> Any:
    fk = ForeignKey("identity.users.id", ondelete="RESTRICT")
    return mapped_column(UUID(as_uuid=True), fk, nullable=nullable)


class ModerationTerm(Base):
    __tablename__ = "moderation_terms"
    __table_args__ = (
        check_in("lang", TERM_LANGS),
        CheckConstraint("severity BETWEEN 1 AND 3", name="severity"),
        check_in("category", CATEGORIES),
        UniqueConstraint("lang", "term_folded"),
        S,
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    lang: Mapped[str] = mapped_column(Text, nullable=False)
    term_folded: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="2")
    category: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_by: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    created_at: Mapped[datetime] = created_at()


class ModerationDecision(Base):
    __tablename__ = "moderation_decisions"
    __table_args__ = (
        check_in("context", CONTEXTS),
        check_in("verdict", VERDICTS),
        Index("ix_moderation_decisions_context_created_at", "context", text("created_at DESC")),
        Index("ix_moderation_decisions_user_id_created_at", "user_id", text("created_at DESC")),
        S,
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    target_ref: Mapped[str | None] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    terms_hit: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    classifier_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = created_at()


class ContentReport(Base):
    __tablename__ = "content_reports"
    __table_args__ = (
        check_in("target_type", REPORT_TARGETS),
        check_in("reason", REPORT_REASONS),
        CheckConstraint("char_length(text) <= 1000", name="text"),
        check_in("status", REPORT_STATUSES),
        Index("ix_content_reports_status_created_at", "status", "created_at"),
        Index("ix_content_reports_target_type_target_id", "target_type", "target_id"),
        S,
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    reporter_user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    resolved_by: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    resolved_at: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at()


class UserRestriction(Base):
    __tablename__ = "user_restrictions"
    __table_args__ = (
        check_in("kind", RESTRICTION_KINDS),
        check_in("scope", SCOPES),
        Index(
            "ix_user_restrictions_user_id", "user_id", postgresql_where=text("lifted_at IS NULL")
        ),
        S,
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk(nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, nullable=False, server_default="global")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    starts_at: Mapped[datetime] = created_at()
    ends_at: Mapped[datetime | None] = tstz()
    created_by: Mapped[uuid.UUID] = _user_fk(nullable=False)
    lifted_at: Mapped[datetime | None] = tstz()

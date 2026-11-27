"""``identity.consent_documents``, ``guardian_consents``, ``privacy_settings`` and
``data_requests`` (01 §4.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, tstz, updated_at, uuid_pk

CONSENT_KINDS = ("guardian_consent", "privacy_policy", "terms")
CONSENT_METHODS = ("otp", "in_person", "other")
REQUEST_KINDS = ("export", "deletion")
REQUEST_STATUSES = ("open", "in_progress", "completed", "rejected")
REQUESTED_VIA = ("app", "support", "guardian", "facebook_callback", "apple_notification")
USERS_ID = "identity.users.id"


def _user_fk(*, nullable: bool = False, primary_key: bool = False) -> Any:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey(USERS_ID, ondelete="RESTRICT"),
        nullable=nullable,
        primary_key=primary_key,
    )


class ConsentDocument(Base):
    __tablename__ = "consent_documents"
    __table_args__ = (
        check_in("lang", ("bn", "en")),
        check_in("kind", CONSENT_KINDS),
        {"schema": "identity"},
    )

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    lang: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    body_sha256: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    published_at: Mapped[datetime] = created_at()


class GuardianConsent(Base):
    __tablename__ = "guardian_consents"
    __table_args__ = (
        check_in("method", CONSENT_METHODS),
        Index(
            "ix_guardian_consents_user_id",
            "user_id",
            postgresql_where=text("withdrawn_at IS NULL"),
        ),
        Index("ix_guardian_consents_guardian_phone_hash", "guardian_phone_hash"),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    guardian_phone_enc: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    guardian_phone_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    consent_version: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    method: Mapped[str] = mapped_column(Text, nullable=False, server_default="otp")
    otp_challenge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.otp_challenges.id")
    )
    granted_at: Mapped[datetime] = created_at()
    withdrawn_at: Mapped[datetime | None] = tstz()


class PrivacySetting(Base):
    __tablename__ = "privacy_settings"
    __table_args__ = (
        check_in("opt_out_by", ("self", "guardian")),
        Index(
            "ix_privacy_settings_hidden",
            "user_id",
            postgresql_where=text("leaderboard_visible = false"),
        ),
        {"schema": "identity"},
    )

    user_id: Mapped[uuid.UUID] = _user_fk(primary_key=True)
    leaderboard_visible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    opt_out_by: Mapped[str | None] = mapped_column(Text)
    profile_private: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    updated_at: Mapped[datetime] = updated_at()


class DataRequest(Base):
    __tablename__ = "data_requests"
    __table_args__ = (
        check_in("kind", REQUEST_KINDS),
        check_in("status", REQUEST_STATUSES),
        check_in("requested_via", REQUESTED_VIA),
        Index("ix_data_requests_status_due_at", "status", "due_at"),
        Index(
            "uq_data_requests_confirmation_code",
            "confirmation_code",
            unique=True,
            postgresql_where=text("confirmation_code IS NOT NULL"),
        ),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = _user_fk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    requested_via: Mapped[str] = mapped_column(Text, nullable=False)
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now() + interval '30 days'")
    )
    completed_at: Mapped[datetime | None] = tstz()
    handled_by: Mapped[uuid.UUID | None] = _user_fk(nullable=True)
    artifact_key: Mapped[str | None] = mapped_column(Text)
    module_status: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    confirmation_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at()

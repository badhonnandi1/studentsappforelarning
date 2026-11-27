"""``identity.otp_challenges``, ``device_sessions`` and ``refresh_tokens`` (01 §4.2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, tstz, uuid_pk

OTP_PURPOSES = ("sign_in", "guardian_consent", "phone_change", "step_up")
PLATFORMS = ("android", "web", "ios")
AUDIENCES = ("api", "admin")
SIGN_IN_METHODS = ("otp", "google", "facebook", "apple", "password", "sso")
REVOKE_REASONS = (
    "user",
    "logout",
    "token_reuse",
    "admin",
    "exam_takeover",
    "account_deleted",
    "session_limit",
    "inactive",
)
LIVE = text("revoked_at IS NULL")
TSTZ = DateTime(timezone=True)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    __table_args__ = (
        check_in("purpose", OTP_PURPOSES),
        CheckConstraint("attempts BETWEEN 0 AND 5", name="attempts"),
        Index("ix_otp_challenges_phone_hash_created_at", "phone_hash", "created_at"),
        Index("ix_otp_challenges_created_at", "created_at"),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    phone_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    phone_enc: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    expires_at: Mapped[datetime] = mapped_column(
        TSTZ, nullable=False, server_default=text("now() + interval '5 min'")
    )
    consumed_at: Mapped[datetime | None] = tstz()
    ip_hash: Mapped[bytes | None] = mapped_column(BYTEA)
    device_id: Mapped[str | None] = mapped_column(Text)
    sms_message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()


class DeviceSession(Base):
    __tablename__ = "device_sessions"
    __table_args__ = (
        check_in("platform", PLATFORMS),
        check_in("audience", AUDIENCES),
        check_in("sign_in_method", SIGN_IN_METHODS),
        check_in("revoke_reason", REVOKE_REASONS),
        CheckConstraint("char_length(user_agent) <= 256", name="user_agent"),
        CheckConstraint("char_length(model) <= 64", name="model"),
        Index("ix_device_sessions_user_id", "user_id", postgresql_where=LIVE),
        Index(
            "uq_device_sessions_live",
            "user_id",
            "device_id",
            "audience",
            unique=True,
            postgresql_where=LIVE,
        ),
        Index("ix_device_sessions_device_id", "device_id"),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.users.id", ondelete="RESTRICT"), nullable=False
    )
    device_id: Mapped[str] = mapped_column(Text, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False)
    audience: Mapped[str] = mapped_column(Text, nullable=False, server_default="api")
    app_version: Mapped[str | None] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[bytes | None] = mapped_column(BYTEA)
    sign_in_method: Mapped[str] = mapped_column(Text, nullable=False)
    exam_epoch: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    restricted_until: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at()
    last_seen_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = tstz()
    revoke_reason: Mapped[str | None] = mapped_column(Text)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
        Index("ix_refresh_tokens_session_id", "session_id"),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity.device_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False, unique=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("identity.refresh_tokens.id")
    )
    issued_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    rotated_at: Mapped[datetime | None] = tstz()
    revoked_at: Mapped[datetime | None] = tstz()

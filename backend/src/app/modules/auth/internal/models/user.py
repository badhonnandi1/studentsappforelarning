"""``identity.users`` and ``identity.external_identities`` (01 §4.2)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, tstz, updated_at, uuid_pk

USER_STATUSES = ("active", "suspended", "pending_deletion", "deleted")
PROVIDERS = ("google", "facebook", "apple")
UNLINK_REASONS = ("user", "deauthorized", "data_deletion", "admin", "apple_revoked")
USERS_ID = "identity.users.id"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        check_in("status", USER_STATUSES),
        CheckConstraint("char_length(display_name) <= 40", name="display_name"),
        CheckConstraint("char_length(first_name) <= 30", name="first_name"),
        check_in("locale", ("bn", "en")),
        CheckConstraint("(status = 'deleted') = (deleted_at IS NOT NULL)", name="deleted_at"),
        Index(
            "uq_users_phone_hash",
            "phone_hash",
            unique=True,
            postgresql_where=text("phone_hash IS NOT NULL"),
        ),
        Index(
            "uq_users_email_hash",
            "email_hash",
            unique=True,
            postgresql_where=text("email_hash IS NOT NULL"),
        ),
        Index("ix_users_status", "status", postgresql_where=text("status <> 'active'")),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    phone_enc: Mapped[bytes | None] = mapped_column(BYTEA)
    phone_hash: Mapped[bytes | None] = mapped_column(BYTEA)
    email_enc: Mapped[bytes | None] = mapped_column(BYTEA)
    email_hash: Mapped[bytes | None] = mapped_column(BYTEA)
    email_verified_at: Mapped[datetime | None] = tstz()
    display_name: Mapped[str | None] = mapped_column(Text)
    first_name: Mapped[str | None] = mapped_column(Text)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    locale: Mapped[str] = mapped_column(Text, nullable=False, server_default="bn")
    created_at: Mapped[datetime] = created_at()
    updated_at: Mapped[datetime] = updated_at()
    last_seen_at: Mapped[datetime | None] = tstz()
    deleted_at: Mapped[datetime | None] = tstz()


class ExternalIdentity(Base):
    __tablename__ = "external_identities"
    __table_args__ = (
        check_in("provider", PROVIDERS),
        check_in("unlink_reason", UNLINK_REASONS),
        UniqueConstraint("provider", "provider_subject"),
        Index(
            "uq_external_identities_user_id_provider",
            "user_id",
            "provider",
            unique=True,
            postgresql_where=text("unlinked_at IS NULL"),
        ),
        Index(
            "ix_external_identities_email_hash",
            "email_hash",
            postgresql_where=text("email_verified"),
        ),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(USERS_ID, ondelete="RESTRICT"), nullable=False
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_subject: Mapped[str] = mapped_column(Text, nullable=False)
    email_enc: Mapped[bytes | None] = mapped_column(BYTEA)
    email_hash: Mapped[bytes | None] = mapped_column(BYTEA)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    display_name: Mapped[str | None] = mapped_column(Text)
    linked_at: Mapped[datetime] = created_at()
    last_login_at: Mapped[datetime | None] = tstz()
    unlinked_at: Mapped[datetime | None] = tstz()
    unlink_reason: Mapped[str | None] = mapped_column(Text)

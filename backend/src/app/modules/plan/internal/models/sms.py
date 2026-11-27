"""``notify.sms_messages`` (monthly partitions) and ``notify.templates`` (01 §3.4)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, Index, Integer, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import BYTEA, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, tstz, updated_at

LANGS = ("bn", "en")
SMS_STATUSES = ("queued", "sent", "delivered", "failed", "fake_sent")
SMS_PURPOSES = ("otp", "guardian_otp", "receipt", "alert", "report", "campaign")
CHANNELS = ("sms", "push", "inbox")


class SmsMessage(Base):
    __tablename__ = "sms_messages"
    __table_args__ = (
        check_in("lang", LANGS),
        CheckConstraint("segments BETWEEN 1 AND 10", name="segments"),
        check_in("status", SMS_STATUSES),
        CheckConstraint("cost_poisha >= 0", name="cost_poisha"),
        check_in("purpose", SMS_PURPOSES),
        Index("ix_sms_messages_to_phone_hash", "to_phone_hash", "created_at"),
        Index(
            "ix_sms_messages_pending",
            "status",
            "created_at",
            postgresql_where=text("status IN ('queued', 'sent')"),
        ),
        {"schema": "notify", "postgresql_partition_by": "RANGE (created_on)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    created_on: Mapped[date] = mapped_column(Date, primary_key=True)
    to_phone_hash: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    to_phone_enc: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    template_code: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="bn")
    segments: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_msg_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    cost_poisha: Mapped[int | None] = mapped_column(BigInteger)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at()
    sent_at: Mapped[datetime | None] = tstz()
    delivered_at: Mapped[datetime | None] = tstz()
    error: Mapped[str | None] = mapped_column(Text)


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (check_in("lang", LANGS), check_in("channel", CHANNELS), {"schema": "notify"})

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    lang: Mapped[str] = mapped_column(Text, primary_key=True)
    channel: Mapped[str] = mapped_column(Text, primary_key=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = updated_at()

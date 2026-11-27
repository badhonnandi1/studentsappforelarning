"""``platform.outbox`` (daily partitions) and ``platform.relay_checkpoints`` (01 §4.1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, Index, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, created_at, tstz, updated_at

EVENT_TYPE_PATTERN = r"^[a-z_]+\.[a-z_.]+$"


class OutboxEvent(Base):
    __tablename__ = "outbox"
    __table_args__ = (
        CheckConstraint(f"event_type ~ '{EVENT_TYPE_PATTERN}'", name="event_type"),
        CheckConstraint("schema_version > 0", name="schema_version"),
        Index("ix_outbox_unrelayed", "recorded_at", postgresql_where=text("relayed_at IS NULL")),
        Index("ix_outbox_aggregate_type_aggregate_id", "aggregate_type", "aggregate_id"),
        {"schema": "platform", "postgresql_partition_by": "RANGE (recorded_on)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    recorded_on: Mapped[date] = mapped_column(Date, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    schema_version: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    track_enrolment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = created_at()
    relayed_at: Mapped[datetime | None] = tstz()
    relay_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")


class RelayCheckpoint(Base):
    __tablename__ = "relay_checkpoints"
    __table_args__ = ({"schema": "platform"},)

    relay_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_recorded_at: Mapped[datetime | None] = tstz()
    last_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    s3_object_key: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = updated_at()

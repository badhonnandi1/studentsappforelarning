"""``platform.jobs``, ``platform.dead_jobs`` and ``platform.processed_events`` (01 §4.1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, Index, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, tstz, uuid_pk
from app.core.jobs.queues import PRIORITY_MAX, PRIORITY_MIN, QUEUES

JOB_STATUSES = ("queued", "running", "done", "failed")
RESOLUTIONS = ("replayed", "discarded", "fixed_manually")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        check_in("queue", QUEUES),
        check_in("status", JOB_STATUSES),
        CheckConstraint(f"priority BETWEEN {PRIORITY_MIN} AND {PRIORITY_MAX}", name="priority"),
        CheckConstraint("max_attempts BETWEEN 1 AND 20", name="max_attempts"),
        Index(
            "ix_jobs_claim",
            "queue",
            text("priority DESC"),
            "run_at",
            postgresql_where=text("status = 'queued'"),
        ),
        Index(
            "ix_jobs_expired_lease",
            "locked_until",
            postgresql_where=text("locked_until IS NOT NULL"),
        ),
        Index(
            "uq_jobs_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        {
            "schema": "platform",
            "postgresql_with": {"fillfactor": "70", "autovacuum_vacuum_scale_factor": "0.01"},
        },
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    queue: Mapped[str] = mapped_column(Text, nullable=False, server_default="default")
    priority: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    run_at: Mapped[datetime] = created_at()
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    max_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="8")
    locked_by: Mapped[str | None] = mapped_column(Text)
    locked_until: Mapped[datetime | None] = tstz()
    last_error: Mapped[str | None] = mapped_column(Text)
    dedupe_key: Mapped[str | None] = mapped_column(Text)
    dedupe_until: Mapped[datetime | None] = tstz()
    created_at: Mapped[datetime] = created_at()


class DeadJob(Base):
    __tablename__ = "dead_jobs"
    __table_args__ = (
        check_in("resolution", RESOLUTIONS),
        Index("ix_dead_jobs_kind_failed_at", "kind", text("failed_at DESC")),
        Index(
            "ix_dead_jobs_unresolved",
            "failed_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        {"schema": "platform"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    original_job_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    queue: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    last_error: Mapped[str] = mapped_column(Text, nullable=False)
    failed_at: Mapped[datetime] = created_at()
    resolved_at: Mapped[datetime | None] = tstz()
    # FK to identity.users(id) is added with that table in b01_06.
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    resolution: Mapped[str | None] = mapped_column(Text)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    __table_args__ = (
        {"schema": "platform", "postgresql_partition_by": "RANGE (event_recorded_on)"},
    )

    consumer: Mapped[str] = mapped_column(Text, primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    event_recorded_on: Mapped[date] = mapped_column(Date, primary_key=True)
    relay_batch_id: Mapped[str | None] = mapped_column(Text)
    processed_at: Mapped[datetime] = created_at()

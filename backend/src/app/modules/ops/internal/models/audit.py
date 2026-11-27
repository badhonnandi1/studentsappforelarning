"""``ops.audit_log``: append-only, monthly partitions (01 §3.5)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, Index, Text
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, created_at

ACTION_PATTERN = r"^[a-z_]+\.[a-z_.]+$"
ACTOR_KINDS = ("staff", "user", "system", "provider")


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        CheckConstraint("actor_kind IN ('staff', 'user', 'system', 'provider')", name="actor_kind"),
        CheckConstraint(f"action ~ '{ACTION_PATTERN}'", name="action"),
        Index("ix_audit_log_target", "target_type", "target_id", "occurred_at"),
        Index("ix_audit_log_actor", "actor_user_id", "occurred_at"),
        Index("ix_audit_log_action", "action", "occurred_at"),
        {"schema": "ops", "postgresql_partition_by": "RANGE (occurred_on)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    occurred_on: Mapped[date] = mapped_column(Date, primary_key=True)
    occurred_at: Mapped[datetime] = created_at()
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="staff")
    actor_roles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    action: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[bytes | None] = mapped_column(BYTEA)
    request_id: Mapped[str | None] = mapped_column(Text)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

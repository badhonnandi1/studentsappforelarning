"""``platform.runtime_config`` and ``platform.idempotency_keys`` (01 §4.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Index, LargeBinary, SmallInteger, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, updated_at

IDEMPOTENT_METHODS = ("POST", "PUT", "PATCH", "DELETE")


class RuntimeConfig(Base):
    __tablename__ = "runtime_config"
    __table_args__ = (
        CheckConstraint("key ~ '^[a-z0-9_.]+$'", name="key"),
        {"schema": "platform"},
    )

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = updated_at()
    # FK to identity.users(id) is added with that table in b01_06.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        check_in("method", IDEMPOTENT_METHODS),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
        {"schema": "platform"},
    )

    # No FK on user_id: anonymous callers are scoped by a device-hash UUID.
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_hash: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    route: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    response: Mapped[Any | None] = mapped_column(JSONB)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = created_at()
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now() + interval '7 days'")
    )

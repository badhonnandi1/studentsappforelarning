"""Declarative ``Base`` with the 01 §1 constraint naming convention, and column helpers."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def updated_at() -> Mapped[datetime]:
    """Set by the application on change (no triggers on hot tables, 01 §1)."""
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def tstz(*, nullable: bool = True) -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


def check_in(column: str, values: Iterable[str], name: str | None = None) -> CheckConstraint:
    """``CHECK (col IN (...))``: enum-like text columns (01 §1, no Postgres ENUM types)."""
    quoted = ", ".join("'" + v.replace("'", "''") + "'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name or column)

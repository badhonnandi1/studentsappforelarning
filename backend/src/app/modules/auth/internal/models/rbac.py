"""``identity.roles``, ``permissions``, ``role_permissions`` and ``role_grants`` (01 §4.2)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db_base import Base, check_in, created_at, tstz, uuid_pk

SCOPE_TYPES = ("global", "track", "subject", "tenant", "batch")
USERS_ID = "identity.users.id"


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (CheckConstraint("code ~ '^[a-z_]+$'", name="code"), {"schema": "identity"})

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name_bn: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)
    is_staff: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        CheckConstraint("code ~ '^[a-z_]+(\\.[a-z_]+)*$'", name="code"),
        {"schema": "identity"},
    )

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    module: Mapped[str] = mapped_column(Text, nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = ({"schema": "identity"},)

    role_code: Mapped[str] = mapped_column(
        Text, ForeignKey("identity.roles.code"), primary_key=True
    )
    permission_code: Mapped[str] = mapped_column(
        Text, ForeignKey("identity.permissions.code"), primary_key=True
    )


class RoleGrant(Base):
    __tablename__ = "role_grants"
    __table_args__ = (
        check_in("scope_type", SCOPE_TYPES),
        CheckConstraint("(scope_type = 'global') = (scope_id IS NULL)", name="scope_id"),
        Index(
            "uq_role_grants_active",
            "user_id",
            "role_code",
            "scope_type",
            "scope_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            postgresql_nulls_not_distinct=True,
        ),
        Index(
            "ix_role_grants_scope_type_scope_id",
            "scope_type",
            "scope_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        {"schema": "identity"},
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(USERS_ID, ondelete="RESTRICT"), nullable=False
    )
    role_code: Mapped[str] = mapped_column(Text, ForeignKey("identity.roles.code"), nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False, server_default="global")
    scope_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey(USERS_ID, ondelete="RESTRICT")
    )
    granted_at: Mapped[datetime] = created_at()
    revoked_at: Mapped[datetime | None] = tstz()

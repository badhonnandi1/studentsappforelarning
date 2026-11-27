"""identity.users, external_identities, otp_challenges; FKs from platform to users.

Revision ID: b01_06
Revises: b01_11

``otp_challenges.purpose`` also allows ``step_up`` (R-25 step-up OTP; 01 lists three purposes).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BYTEA, UUID

revision = "b01_06"
down_revision = "b01_11"
branch_labels = None
depends_on = None

S = "identity"
TSTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
USER_STATUSES = "'active', 'suspended', 'pending_deletion', 'deleted'"
PROVIDERS = "'google', 'facebook', 'apple'"
UNLINK = "'user', 'deauthorized', 'data_deletion', 'admin', 'apple_revoked'"
OTP_PURPOSES = "'sign_in', 'guardian_consent', 'phone_change', 'step_up'"
USERS_FK = [
    ("dead_jobs", "resolved_by", "fk_dead_jobs_resolved_by"),
    ("runtime_config", "updated_by", "fk_runtime_config_updated_by"),
]


def uuid_col(name: str, **kw: object) -> sa.Column[object]:
    return sa.Column(name, UUID(as_uuid=True), **kw)  # type: ignore[arg-type]


def users_fk(column: str = "user_id", **kw: object) -> sa.Column[object]:
    fk = sa.ForeignKey("identity.users.id", ondelete="RESTRICT")
    return sa.Column(column, UUID(as_uuid=True), fk, **kw)  # type: ignore[arg-type]


def upgrade() -> None:
    op.create_table(
        "users",
        uuid_col("id", primary_key=True),
        sa.Column("status", sa.Text, nullable=False, server_default="active"),
        sa.Column("phone_enc", BYTEA),
        sa.Column("phone_hash", BYTEA),
        sa.Column("email_enc", BYTEA),
        sa.Column("email_hash", BYTEA),
        sa.Column("email_verified_at", TSTZ),
        sa.Column("display_name", sa.Text),
        sa.Column("first_name", sa.Text),
        sa.Column("date_of_birth", sa.Date),
        sa.Column("locale", sa.Text, nullable=False, server_default="bn"),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("last_seen_at", TSTZ),
        sa.Column("deleted_at", TSTZ),
        sa.CheckConstraint(f"status IN ({USER_STATUSES})", name="status"),
        sa.CheckConstraint("char_length(display_name) <= 40", name="display_name"),
        sa.CheckConstraint("char_length(first_name) <= 30", name="first_name"),
        sa.CheckConstraint("locale IN ('bn', 'en')", name="locale"),
        sa.CheckConstraint("(status = 'deleted') = (deleted_at IS NOT NULL)", name="deleted_at"),
        schema=S,
    )
    where = sa.text
    op.create_index(
        "uq_users_phone_hash", "users", ["phone_hash"], unique=True, schema=S,
        postgresql_where=where("phone_hash IS NOT NULL"),
    )  # fmt: skip
    op.create_index(
        "uq_users_email_hash", "users", ["email_hash"], unique=True, schema=S,
        postgresql_where=where("email_hash IS NOT NULL"),
    )  # fmt: skip
    op.create_index(
        "ix_users_status", "users", ["status"], schema=S,
        postgresql_where=where("status <> 'active'"),
    )  # fmt: skip
    for table, column, name in USERS_FK:
        op.create_foreign_key(
            name, table, "users", [column], ["id"],
            source_schema="platform", referent_schema=S, ondelete="RESTRICT",
        )  # fmt: skip
    op.create_table(
        "external_identities",
        uuid_col("id", primary_key=True),
        users_fk(nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("provider_subject", sa.Text, nullable=False),
        sa.Column("email_enc", BYTEA),
        sa.Column("email_hash", BYTEA),
        sa.Column("email_verified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("display_name", sa.Text),
        sa.Column("linked_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("last_login_at", TSTZ),
        sa.Column("unlinked_at", TSTZ),
        sa.Column("unlink_reason", sa.Text),
        sa.CheckConstraint(f"provider IN ({PROVIDERS})", name="provider"),
        sa.CheckConstraint(f"unlink_reason IN ({UNLINK})", name="unlink_reason"),
        sa.UniqueConstraint("provider", "provider_subject"),
        schema=S,
    )
    op.create_index(
        "uq_external_identities_user_id_provider", "external_identities",
        ["user_id", "provider"], unique=True, schema=S,
        postgresql_where=where("unlinked_at IS NULL"),
    )  # fmt: skip
    op.create_index(
        "ix_external_identities_email_hash", "external_identities", ["email_hash"], schema=S,
        postgresql_where=where("email_verified"),
    )  # fmt: skip
    op.create_table(
        "otp_challenges",
        uuid_col("id", primary_key=True),
        sa.Column("phone_hash", BYTEA, nullable=False),
        sa.Column("phone_enc", BYTEA, nullable=False),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("code_hash", BYTEA, nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column(
            "expires_at", TSTZ, nullable=False, server_default=sa.text("now() + interval '5 min'")
        ),
        sa.Column("consumed_at", TSTZ),
        sa.Column("ip_hash", BYTEA),
        sa.Column("device_id", sa.Text),
        uuid_col("sms_message_id"),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.CheckConstraint(f"purpose IN ({OTP_PURPOSES})", name="purpose"),
        sa.CheckConstraint("attempts BETWEEN 0 AND 5", name="attempts"),
        schema=S,
    )
    op.create_index(
        "ix_otp_challenges_phone_hash_created_at", "otp_challenges",
        ["phone_hash", "created_at"], schema=S,
    )  # fmt: skip
    op.create_index("ix_otp_challenges_created_at", "otp_challenges", ["created_at"], schema=S)


def downgrade() -> None:
    op.drop_table("otp_challenges", schema=S)
    op.drop_table("external_identities", schema=S)
    for table, _column, name in USERS_FK:
        op.drop_constraint(name, table, schema="platform", type_="foreignkey")
    op.drop_table("users", schema=S)

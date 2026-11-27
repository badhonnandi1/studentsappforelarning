"""ops.audit_log: append-only, partitioned monthly, 3 months ahead (01 §3.5).

``app_rw`` keeps SELECT and INSERT only; UPDATE and DELETE are revoked on the parent, and the
partition helper copies exactly those grants onto every child partition.

Revision ID: b01_05
Revises: b01_04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA, JSONB, UUID

from migrations.helpers.partitions import create_partitions_sql

revision = "b01_05"
down_revision = "b01_04"
branch_labels = None
depends_on = None

S = "ops"
APP_ROLE = "app_rw"


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("occurred_on", sa.Date, primary_key=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_user_id", UUID(as_uuid=True)),
        sa.Column("actor_kind", sa.Text, nullable=False, server_default="staff"),
        sa.Column("actor_roles", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("module", sa.Text, nullable=False),
        sa.Column("target_type", sa.Text, nullable=False),
        sa.Column("target_id", sa.Text, nullable=False),
        sa.Column("before", JSONB),
        sa.Column("after", JSONB),
        sa.Column("reason", sa.Text),
        sa.Column("ip_hash", BYTEA),
        sa.Column("request_id", sa.Text),
        sa.Column("tenant_id", UUID(as_uuid=True)),
        sa.CheckConstraint(
            "actor_kind IN ('staff', 'user', 'system', 'provider')", name="actor_kind"
        ),
        sa.CheckConstraint("action ~ '^[a-z_]+\\.[a-z_.]+$'", name="action"),
        schema=S,
        postgresql_partition_by="RANGE (occurred_on)",
    )
    for name, columns in (
        ("ix_audit_log_target", ["target_type", "target_id", "occurred_at"]),
        ("ix_audit_log_actor", ["actor_user_id", "occurred_at"]),
        ("ix_audit_log_action", ["action", "occurred_at"]),
    ):
        op.create_index(name, "audit_log", columns, schema=S)
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON {S}.audit_log FROM {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON {S}.audit_log TO {APP_ROLE}")
    op.execute(create_partitions_sql("ops.audit_log", "month", 3))


def downgrade() -> None:
    op.drop_table("audit_log", schema=S)

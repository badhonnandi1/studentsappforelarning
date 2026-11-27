"""Outbox and processed_events: partitioned parents plus 7 days of partitions ahead.

Revision ID: b01_04
Revises: b01_03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from migrations.helpers.partitions import create_partitions_sql

revision = "b01_04"
down_revision = "b01_03"
branch_labels = None
depends_on = None

S = "platform"
TSTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "outbox",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("recorded_on", sa.Date, primary_key=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("schema_version", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("aggregate_type", sa.Text, nullable=False),
        sa.Column("aggregate_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True)),
        sa.Column("track_enrolment_id", UUID(as_uuid=True)),
        sa.Column("tenant_id", UUID(as_uuid=True)),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("occurred_at", TSTZ, nullable=False),
        sa.Column("recorded_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("relayed_at", TSTZ),
        sa.Column("relay_attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.CheckConstraint("event_type ~ '^[a-z_]+\\.[a-z_.]+$'", name="event_type"),
        sa.CheckConstraint("schema_version > 0", name="schema_version"),
        schema=S,
        postgresql_partition_by="RANGE (recorded_on)",
    )
    op.create_index(
        "ix_outbox_unrelayed",
        "outbox",
        ["recorded_at"],
        schema=S,
        postgresql_where=sa.text("relayed_at IS NULL"),
    )
    op.create_index(
        "ix_outbox_aggregate_type_aggregate_id",
        "outbox",
        ["aggregate_type", "aggregate_id"],
        schema=S,
    )
    op.create_table(
        "processed_events",
        sa.Column("consumer", sa.Text, primary_key=True),
        sa.Column("event_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_recorded_on", sa.Date, primary_key=True),
        sa.Column("relay_batch_id", sa.Text),
        sa.Column("processed_at", TSTZ, nullable=False, server_default=NOW),
        schema=S,
        postgresql_partition_by="RANGE (event_recorded_on)",
    )
    op.execute(create_partitions_sql("platform.outbox", "day", 7))
    op.execute(create_partitions_sql("platform.processed_events", "day", 7))


def downgrade() -> None:
    op.drop_table("processed_events", schema=S)
    op.drop_table("outbox", schema=S)

"""Platform job queue, dead jobs, runtime config, relay checkpoints, idempotency keys.

Revision ID: b01_03
Revises: b01_02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.jobs.queues import PRIORITY_MAX, PRIORITY_MIN, QUEUES

revision = "b01_03"
down_revision = "b01_02"
branch_labels = None
depends_on = None

S = "platform"
TSTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")


def _in(column: str, values: tuple[str, ...]) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{column} IN ({', '.join(repr(v) for v in values)})", name=column)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("queue", sa.Text, nullable=False, server_default="default"),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("run_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("attempts", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.SmallInteger, nullable=False, server_default="8"),
        sa.Column("locked_by", sa.Text),
        sa.Column("locked_until", TSTZ),
        sa.Column("last_error", sa.Text),
        sa.Column("dedupe_key", sa.Text),
        sa.Column("dedupe_until", TSTZ),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        _in("queue", QUEUES),
        _in("status", ("queued", "running", "done", "failed")),
        sa.CheckConstraint(f"priority BETWEEN {PRIORITY_MIN} AND {PRIORITY_MAX}", name="priority"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 20", name="max_attempts"),
        schema=S,
        postgresql_with={"fillfactor": "70", "autovacuum_vacuum_scale_factor": "0.01"},
    )
    op.create_index(
        "ix_jobs_claim",
        "jobs",
        ["queue", sa.text("priority DESC"), "run_at"],
        schema=S,
        postgresql_where=sa.text("status = 'queued'"),
    )
    op.create_index(
        "ix_jobs_expired_lease",
        "jobs",
        ["locked_until"],
        schema=S,
        postgresql_where=sa.text("locked_until IS NOT NULL"),
    )
    op.create_index(
        "uq_jobs_dedupe_key",
        "jobs",
        ["dedupe_key"],
        unique=True,
        schema=S,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )
    op.create_table(
        "dead_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("original_job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("queue", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("attempts", sa.SmallInteger, nullable=False),
        sa.Column("last_error", sa.Text, nullable=False),
        sa.Column("failed_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("resolved_at", TSTZ),
        sa.Column("resolved_by", UUID(as_uuid=True)),
        sa.Column("resolution", sa.Text),
        _in("resolution", ("replayed", "discarded", "fixed_manually")),
        schema=S,
    )
    op.create_index(
        "ix_dead_jobs_kind_failed_at", "dead_jobs", ["kind", sa.text("failed_at DESC")], schema=S
    )
    op.create_index(
        "ix_dead_jobs_unresolved",
        "dead_jobs",
        ["failed_at"],
        schema=S,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_table(
        "runtime_config",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", JSONB, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("updated_by", UUID(as_uuid=True)),
        sa.CheckConstraint("key ~ '^[a-z0-9_.]+$'", name="key"),
        schema=S,
    )
    op.create_table(
        "relay_checkpoints",
        sa.Column("relay_name", sa.Text, primary_key=True),
        sa.Column("last_recorded_at", TSTZ),
        sa.Column("last_event_id", UUID(as_uuid=True)),
        sa.Column("s3_object_key", sa.Text),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
        schema=S,
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("key", UUID(as_uuid=True), primary_key=True),
        sa.Column("request_hash", sa.LargeBinary, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("route", sa.Text, nullable=False),
        sa.Column("status_code", sa.SmallInteger),
        sa.Column("response", JSONB),
        sa.Column("resource_id", UUID(as_uuid=True)),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column(
            "expires_at", TSTZ, nullable=False, server_default=sa.text("now() + interval '7 days'")
        ),
        _in("method", ("POST", "PUT", "PATCH", "DELETE")),
        schema=S,
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"], schema=S)


def downgrade() -> None:
    for table in ("idempotency_keys", "relay_checkpoints", "runtime_config", "dead_jobs", "jobs"):
        op.drop_table(table, schema=S)

"""community.moderation_terms, moderation_decisions, content_reports, user_restrictions.

Revision ID: b01_12
Revises: b01_10

Where 05's API and 01's CHECK lists differ, the CHECK takes both: report ``target_type`` adds
``profile_photo`` and ``other`` (API), restriction ``scope`` adds ``profile`` (API; ``all`` is
stored as ``global``), and decision ``context`` adds ``content_report`` (report text is
moderated, 05 §D).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "b01_12"
down_revision = "b01_10"
branch_labels = None
depends_on = None

S = "community"
TSTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
USERS = "identity.users.id"
CONTEXTS = (
    "display_name", "profile_photo", "error_report", "ticket", "tutor_input", "tutor_output",
    "post", "group_message", "content_report",
)  # fmt: skip
TARGETS = (
    "user", "display_name", "profile_photo", "post", "thread", "group_message",
    "tutor_message", "other",
)  # fmt: skip


def _in(column: str, *values: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(f"{column} IN ({', '.join(repr(v) for v in values)})", name=column)


def _user(name: str, *, nullable: bool) -> sa.Column[object]:
    fk = sa.ForeignKey(USERS, ondelete="RESTRICT")
    return sa.Column(name, UUID(as_uuid=True), fk, nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "moderation_terms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("lang", sa.Text, nullable=False),
        sa.Column("term_folded", sa.Text, nullable=False),
        sa.Column("severity", sa.SmallInteger, nullable=False, server_default="2"),
        sa.Column("category", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        _user("created_by", nullable=True),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        _in("lang", "bn", "en", "banglish"),
        sa.CheckConstraint("severity BETWEEN 1 AND 3", name="severity"),
        _in("category", "profanity", "sexual", "hate", "self_harm", "contact_info", "spam"),
        sa.UniqueConstraint("lang", "term_folded"),
        schema=S,
    )
    op.create_table(
        "moderation_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _user("user_id", nullable=True),
        sa.Column("context", sa.Text, nullable=False),
        sa.Column("target_ref", sa.Text),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("terms_hit", ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("classifier_score", sa.Numeric(4, 3)),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        _in("context", *CONTEXTS),
        _in("verdict", "flag", "block"),
        schema=S,
    )
    for col in ("context", "user_id"):
        name = f"ix_moderation_decisions_{col}_created_at"
        op.create_index(name, "moderation_decisions", [col, sa.text("created_at DESC")], schema=S)
    op.create_table(
        "content_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _user("reporter_user_id", nullable=False),
        sa.Column("target_type", sa.Text, nullable=False),
        sa.Column("target_id", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("text", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        _user("resolved_by", nullable=True),
        sa.Column("resolved_at", TSTZ),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        _in("target_type", *TARGETS),
        _in("reason", "abuse", "spam", "sexual", "self_harm", "privacy", "cheating", "other"),
        sa.CheckConstraint("char_length(text) <= 1000", name="text"),
        _in("status", "open", "actioned", "dismissed"),
        schema=S,
    )
    op.create_index(
        "ix_content_reports_status_created_at",
        "content_reports",
        ["status", "created_at"],
        schema=S,
    )
    op.create_index(
        "ix_content_reports_target_type_target_id",
        "content_reports",
        ["target_type", "target_id"],
        schema=S,
    )
    op.create_table(
        "user_restrictions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        _user("user_id", nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("scope", sa.Text, nullable=False, server_default="global"),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("starts_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("ends_at", TSTZ),
        _user("created_by", nullable=False),
        sa.Column("lifted_at", TSTZ),
        _in("kind", "mute", "ban"),
        _in("scope", "global", "community", "tutor", "display_name", "profile"),
        schema=S,
    )
    op.create_index(
        "ix_user_restrictions_user_id",
        "user_restrictions",
        ["user_id"],
        schema=S,
        postgresql_where=sa.text("lifted_at IS NULL"),
    )


def downgrade() -> None:
    for table in (
        "user_restrictions",
        "content_reports",
        "moderation_decisions",
        "moderation_terms",
    ):
        op.drop_table(table, schema=S)

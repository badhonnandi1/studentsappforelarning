"""identity.device_sessions and identity.refresh_tokens.

Revision ID: b01_07
Revises: b01_06

Additions to 01 §4.2, each needed by a B1 rule:
- ``audience`` (api/admin): staff sessions get 12 h refresh tokens and ``aud=admin`` (R-07);
- ``sign_in_method`` also allows ``sso`` for staff;
- ``restricted_until``: the 72 h restricted mode after a dormant new-device sign-in (R-25);
- a partial unique ``(user_id, device_id)`` on live sessions: one session per device (C.4).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BYTEA, UUID

revision = "b01_07"
down_revision = "b01_06"
branch_labels = None
depends_on = None

S = "identity"
TSTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
METHODS = "'otp', 'google', 'facebook', 'apple', 'password', 'sso'"
REASONS = (
    "'user', 'logout', 'token_reuse', 'admin', 'exam_takeover', 'account_deleted', 'session_limit'"
)


def upgrade() -> None:
    op.create_table(
        "device_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("identity.users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("device_id", sa.Text, nullable=False),
        sa.Column("platform", sa.Text, nullable=False),
        sa.Column("audience", sa.Text, nullable=False, server_default="api"),
        sa.Column("app_version", sa.Text),
        sa.Column("user_agent", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("ip_hash", BYTEA),
        sa.Column("sign_in_method", sa.Text, nullable=False),
        sa.Column("exam_epoch", sa.Integer, nullable=False, server_default="0"),
        sa.Column("restricted_until", TSTZ),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("last_seen_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("revoked_at", TSTZ),
        sa.Column("revoke_reason", sa.Text),
        sa.CheckConstraint("platform IN ('android', 'web', 'ios')", name="platform"),
        sa.CheckConstraint("audience IN ('api', 'admin')", name="audience"),
        sa.CheckConstraint(f"sign_in_method IN ({METHODS})", name="sign_in_method"),
        sa.CheckConstraint(f"revoke_reason IN ({REASONS})", name="revoke_reason"),
        sa.CheckConstraint("char_length(user_agent) <= 256", name="user_agent"),
        sa.CheckConstraint("char_length(model) <= 64", name="model"),
        schema=S,
    )
    op.create_index(
        "ix_device_sessions_user_id",
        "device_sessions",
        ["user_id"],
        schema=S,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "uq_device_sessions_live",
        "device_sessions",
        ["user_id", "device_id", "audience"],
        unique=True,
        schema=S,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("ix_device_sessions_device_id", "device_sessions", ["device_id"], schema=S)
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("identity.device_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("family_id", UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", BYTEA, nullable=False, unique=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("identity.refresh_tokens.id")),
        sa.Column("issued_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("expires_at", TSTZ, nullable=False),
        sa.Column("rotated_at", TSTZ),
        sa.Column("revoked_at", TSTZ),
        schema=S,
    )
    op.create_index("ix_refresh_tokens_family_id", "refresh_tokens", ["family_id"], schema=S)
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"], schema=S)
    op.create_index("ix_refresh_tokens_session_id", "refresh_tokens", ["session_id"], schema=S)


def downgrade() -> None:
    op.drop_table("refresh_tokens", schema=S)
    op.drop_table("device_sessions", schema=S)

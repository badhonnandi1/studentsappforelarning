"""identity.profiles, consent_documents, guardian_consents, privacy_settings, data_requests.

Revision ID: b01_10
Revises: b01_09

``profiles.class_level`` allows 13 (admission) and 14 (job) for the two non-class stages that
05 §C.4 names; 01's CHECK stopped at 12. ``board_code`` gets its FK in B2.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BYTEA, JSONB, UUID

revision = "b01_10"
down_revision = "b01_09"
branch_labels = None
depends_on = None

S = "identity"
TSTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
USERS = "identity.users.id"
VIA = "'app', 'support', 'guardian', 'facebook_callback', 'apple_notification'"


def user_fk(name: str = "user_id", **kw: object) -> sa.Column[object]:
    fk = sa.ForeignKey(USERS, ondelete="RESTRICT")
    return sa.Column(name, UUID(as_uuid=True), fk, **kw)  # type: ignore[arg-type]


def upgrade() -> None:
    op.create_table(
        "profiles",
        user_fk(primary_key=True),
        sa.Column("class_level", sa.SmallInteger),
        sa.Column("group_code", sa.Text),
        sa.Column("version_lang", sa.Text),
        sa.Column("curriculum", sa.Text),
        sa.Column("institution_id", UUID(as_uuid=True), sa.ForeignKey("identity.institutions.id")),
        sa.Column("district_id", sa.SmallInteger, sa.ForeignKey("identity.districts.id")),
        sa.Column("upazila_id", sa.Integer, sa.ForeignKey("identity.upazilas.id")),
        sa.Column("board_code", sa.Text),
        sa.Column("exam_year", sa.SmallInteger),
        sa.Column("photo_key", sa.Text),
        sa.Column("photo_status", sa.Text, nullable=False, server_default="none"),
        sa.Column("reply_lang_pref", sa.Text, nullable=False, server_default="auto"),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
        sa.CheckConstraint("class_level BETWEEN 6 AND 14", name="class_level"),
        sa.CheckConstraint(
            "group_code IN ('science', 'business', 'humanities', 'general')", name="group_code"
        ),
        sa.CheckConstraint("version_lang IN ('bn', 'en')", name="version_lang"),
        sa.CheckConstraint("curriculum IN ('general', 'madrasah', 'technical')", name="curriculum"),
        sa.CheckConstraint("exam_year BETWEEN 2025 AND 2040", name="exam_year"),
        sa.CheckConstraint(
            "photo_status IN ('none', 'pending', 'approved', 'rejected')", name="photo_status"
        ),
        sa.CheckConstraint(
            "reply_lang_pref IN ('auto', 'bn', 'en', 'banglish')", name="reply_lang_pref"
        ),
        schema=S,
    )
    op.create_index("ix_profiles_institution_id", "profiles", ["institution_id"], schema=S)
    op.create_index("ix_profiles_district_id", "profiles", ["district_id"], schema=S)
    op.create_table(
        "consent_documents",
        sa.Column("version", sa.Text, primary_key=True),
        sa.Column("lang", sa.Text, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("body_sha256", BYTEA, nullable=False),
        sa.Column("published_at", TSTZ, nullable=False, server_default=NOW),
        sa.CheckConstraint("lang IN ('bn', 'en')", name="lang"),
        sa.CheckConstraint("kind IN ('guardian_consent', 'privacy_policy', 'terms')", name="kind"),
        schema=S,
    )
    op.create_table(
        "guardian_consents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        user_fk(nullable=False),
        sa.Column("guardian_phone_enc", BYTEA, nullable=False),
        sa.Column("guardian_phone_hash", BYTEA, nullable=False),
        sa.Column("consent_version", sa.Text, nullable=False),
        sa.Column("scope", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("method", sa.Text, nullable=False, server_default="otp"),
        sa.Column(
            "otp_challenge_id", UUID(as_uuid=True), sa.ForeignKey("identity.otp_challenges.id")
        ),
        sa.Column("granted_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("withdrawn_at", TSTZ),
        sa.CheckConstraint("method IN ('otp', 'in_person', 'other')", name="method"),
        schema=S,
    )
    op.create_index(
        "ix_guardian_consents_user_id",
        "guardian_consents",
        ["user_id"],
        schema=S,
        postgresql_where=sa.text("withdrawn_at IS NULL"),
    )
    op.create_index(
        "ix_guardian_consents_guardian_phone_hash",
        "guardian_consents",
        ["guardian_phone_hash"],
        schema=S,
    )
    op.create_table(
        "privacy_settings",
        user_fk(primary_key=True),
        sa.Column("leaderboard_visible", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("opt_out_by", sa.Text),
        sa.Column("profile_private", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
        sa.CheckConstraint("opt_out_by IN ('self', 'guardian')", name="opt_out_by"),
        schema=S,
    )
    op.create_index(
        "ix_privacy_settings_hidden",
        "privacy_settings",
        ["user_id"],
        schema=S,
        postgresql_where=sa.text("leaderboard_visible = false"),
    )
    op.create_table(
        "data_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        user_fk(nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="open"),
        sa.Column("requested_via", sa.Text, nullable=False),
        sa.Column(
            "due_at", TSTZ, nullable=False, server_default=sa.text("now() + interval '30 days'")
        ),
        sa.Column("completed_at", TSTZ),
        user_fk("handled_by"),
        sa.Column("artifact_key", sa.Text),
        sa.Column("module_status", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("confirmation_code", sa.Text),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.CheckConstraint("kind IN ('export', 'deletion')", name="kind"),
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'completed', 'rejected')", name="status"
        ),
        sa.CheckConstraint(f"requested_via IN ({VIA})", name="requested_via"),
        schema=S,
    )
    op.create_index(
        "ix_data_requests_status_due_at", "data_requests", ["status", "due_at"], schema=S
    )
    op.create_index(
        "uq_data_requests_confirmation_code",
        "data_requests",
        ["confirmation_code"],
        unique=True,
        schema=S,
        postgresql_where=sa.text("confirmation_code IS NOT NULL"),
    )


def downgrade() -> None:
    for table in (
        "data_requests", "privacy_settings", "guardian_consents", "consent_documents", "profiles"
    ):  # fmt: skip
        op.drop_table(table, schema=S)

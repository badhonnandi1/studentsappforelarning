"""notify.sms_messages (monthly partitions, 3 ahead) and notify.templates with OTP seeds.

Revision ID: b01_11
Revises: b01_05

The SMS transport has no dependency on identity, so it lands before the AUTH revisions that
need it (``b01_06``..``b01_10`` revise this one). ``fake_sent`` is the fake adapter's status
(05 §A risk table).
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import BYTEA, UUID

from migrations.helpers.partitions import create_partitions_sql

revision = "b01_11"
down_revision = "b01_05"
branch_labels = None
depends_on = None

S = "notify"
TSTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
STATUSES = "'queued', 'sent', 'delivered', 'failed', 'fake_sent'"
PURPOSES = "'otp', 'guardian_otp', 'receipt', 'alert', 'report', 'campaign'"
TEMPLATES = [
    ("auth.otp", "bn", "আপনার যাচাই কোড {code}। ৫ মিনিটের মধ্যে ব্যবহার করুন। কোডটি কাউকে জানাবেন না।"),
    (
        "auth.otp",
        "en",
        "Your verification code is {code}. It expires in 5 minutes. Do not share it.",
    ),
    (
        "auth.guardian_otp",
        "bn",
        "সন্তানের অ্যাকাউন্টে সম্মতির কোড {code}। ৫ মিনিটের মধ্যে ব্যবহার করুন। কাউকে জানাবেন না।",
    ),
    (
        "auth.guardian_otp",
        "en",
        "Your child's account consent code is {code}. It expires in 5 minutes. Do not share it.",
    ),
]


def upgrade() -> None:
    op.create_table(
        "sms_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_on", sa.Date, primary_key=True),
        sa.Column("to_phone_hash", BYTEA, nullable=False),
        sa.Column("to_phone_enc", BYTEA, nullable=False),
        sa.Column("template_code", sa.Text, nullable=False),
        sa.Column("lang", sa.Text, nullable=False, server_default="bn"),
        sa.Column("segments", sa.SmallInteger, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("provider_msg_id", sa.Text),
        sa.Column("status", sa.Text, nullable=False, server_default="queued"),
        sa.Column("cost_poisha", sa.BigInteger),
        sa.Column("purpose", sa.Text, nullable=False),
        sa.Column("created_at", TSTZ, nullable=False, server_default=NOW),
        sa.Column("sent_at", TSTZ),
        sa.Column("delivered_at", TSTZ),
        sa.Column("error", sa.Text),
        sa.CheckConstraint("lang IN ('bn', 'en')", name="lang"),
        sa.CheckConstraint("segments BETWEEN 1 AND 10", name="segments"),
        sa.CheckConstraint(f"status IN ({STATUSES})", name="status"),
        sa.CheckConstraint("cost_poisha >= 0", name="cost_poisha"),
        sa.CheckConstraint(f"purpose IN ({PURPOSES})", name="purpose"),
        schema=S,
        postgresql_partition_by="RANGE (created_on)",
    )
    op.create_index(
        "ix_sms_messages_to_phone_hash", "sms_messages", ["to_phone_hash", "created_at"], schema=S
    )
    op.create_index(
        "ix_sms_messages_pending",
        "sms_messages",
        ["status", "created_at"],
        schema=S,
        postgresql_where=sa.text("status IN ('queued', 'sent')"),
    )
    op.execute(create_partitions_sql("notify.sms_messages", "month", 3))
    templates = op.create_table(
        "templates",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("lang", sa.Text, primary_key=True),
        sa.Column("channel", sa.Text, primary_key=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("updated_at", TSTZ, nullable=False, server_default=NOW),
        sa.CheckConstraint("lang IN ('bn', 'en')", name="lang"),
        sa.CheckConstraint("channel IN ('sms', 'push', 'inbox')", name="channel"),
        schema=S,
    )
    seeded = datetime(2026, 1, 1, tzinfo=UTC)
    op.bulk_insert(
        templates,
        [
            {"code": c, "lang": lang, "channel": "sms", "body": b, "updated_at": seeded}
            for c, lang, b in TEMPLATES
        ],
    )


def downgrade() -> None:
    op.drop_table("templates", schema=S)
    op.drop_table("sms_messages", schema=S)

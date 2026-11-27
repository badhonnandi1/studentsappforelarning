"""identity.districts, upazilas, institutions (empty; ``scripts/seed_reference.py`` loads them).

Revision ID: b01_09
Revises: b01_08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b01_09"
down_revision = "b01_08"
branch_labels = None
depends_on = None

S = "identity"
KINDS = (
    "'school', 'college', 'school_college', 'madrasah', 'technical', 'university', "
    "'coaching', 'other'"
)


def upgrade() -> None:
    op.create_table(
        "districts",
        sa.Column("id", sa.SmallInteger, primary_key=True, autoincrement=False),
        sa.Column("division", sa.Text, nullable=False),
        sa.Column("name_bn", sa.Text, nullable=False),
        sa.Column("name_en", sa.Text, nullable=False, unique=True),
        schema=S,
    )
    op.create_table(
        "upazilas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column(
            "district_id", sa.SmallInteger, sa.ForeignKey("identity.districts.id"), nullable=False
        ),
        sa.Column("name_bn", sa.Text, nullable=False),
        sa.Column("name_en", sa.Text, nullable=False),
        sa.UniqueConstraint("district_id", "name_en"),
        schema=S,
    )
    op.create_table(
        "institutions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("eiin", sa.Text),
        sa.Column("name_bn", sa.Text, nullable=False),
        sa.Column("name_en", sa.Text, nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column(
            "district_id", sa.SmallInteger, sa.ForeignKey("identity.districts.id"), nullable=False
        ),
        sa.Column("upazila_id", sa.Integer, sa.ForeignKey("identity.upazilas.id")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("source", sa.Text, nullable=False, server_default="seed"),
        sa.CheckConstraint(f"kind IN ({KINDS})", name="kind"),
        sa.CheckConstraint("source IN ('seed', 'user_suggested', 'ops')", name="source"),
        schema=S,
    )
    op.create_index(
        "uq_institutions_eiin",
        "institutions",
        ["eiin"],
        unique=True,
        schema=S,
        postgresql_where=sa.text("eiin IS NOT NULL"),
    )
    op.create_index("ix_institutions_district_id", "institutions", ["district_id"], schema=S)
    for column in ("name_bn", "name_en"):
        op.create_index(
            f"ix_institutions_{column}_trgm",
            "institutions",
            [column],
            schema=S,
            postgresql_using="gin",
            postgresql_ops={column: "gin_trgm_ops"},
        )


def downgrade() -> None:
    op.drop_table("institutions", schema=S)
    op.drop_table("upazilas", schema=S)
    op.drop_table("districts", schema=S)

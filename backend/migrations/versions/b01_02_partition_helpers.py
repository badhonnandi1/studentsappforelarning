"""Partition helper functions (01 §1.2).

Revision ID: b01_02
Revises: b01_01
"""

from __future__ import annotations

from alembic import op

from migrations.helpers import partitions

revision = "b01_02"
down_revision = "b01_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(partitions.CREATE_RANGE_PARTITIONS)
    op.execute(partitions.DROP_PARTITIONS_BEFORE)
    for statement in partitions.grant_sql():
        op.execute(statement)


def downgrade() -> None:
    for signature in partitions.FUNCTIONS:
        op.execute(f"DROP FUNCTION platform.{signature}")

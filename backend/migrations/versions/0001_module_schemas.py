"""Create one PostgreSQL schema per server-owned module (v2 §2.4). No tables yet.

Revision ID: 0001
Revises:
Create Date: 2026-11-27
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

# Frozen copy of app.modules.registry.SCHEMAS; tests/test_modules.py keeps them equal.
SCHEMAS = (
    "identity",  # AUTH
    "curriculum",  # TAX
    "qbank",  # QB
    "cms",  # CMS
    "practice",  # PRAC
    "exam",  # EXAM
    "analytics",  # ANL
    "ai",  # AI
    "rewards",  # GAM
    "notify",  # PLAN
    "community",  # COM
    "parent",  # PAR
    "institution",  # INST
    "commerce",  # PAY
    "ops",  # OPS
    "platform",  # NFR: outbox, job queue, idempotency keys
)


def upgrade() -> None:
    for schema in SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{schema}" RESTRICT')

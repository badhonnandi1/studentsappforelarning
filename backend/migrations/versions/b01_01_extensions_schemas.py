"""Extensions, the 16 module schemas, and the app_rw role with default privileges.

Revision ID: b01_01
Revises:
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b01_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copy of app.modules.registry.SCHEMAS at this revision; test_registry keeps them equal.
SCHEMAS = (
    "platform",
    "identity",
    "community",
    "notify",
    "ops",
    "curriculum",
    "qbank",
    "cms",
    "practice",
    "exam",
    "analytics",
    "ai",
    "rewards",
    "commerce",
    "institution",
    "parent",
)
EXTENSIONS = ("vector", "pg_trgm", "ltree", "btree_gist", "pgcrypto")
APP_ROLE = "app_rw"


def upgrade() -> None:
    for ext in EXTENSIONS:
        op.execute(f'CREATE EXTENSION IF NOT EXISTS "{ext}"')
    # The role is normally created by infrastructure with a password; create a NOLOGIN
    # placeholder only when it is missing so migrations run on a bare database.
    op.execute(
        f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') "
        f"THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$"
    )
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {APP_ROLE}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}"
        )


def downgrade() -> None:
    for schema in reversed(SCHEMAS):
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM {APP_ROLE}"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
            f"REVOKE USAGE, SELECT ON SEQUENCES FROM {APP_ROLE}"
        )
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    # Extensions and the role are left in place: other databases on the cluster may use them.

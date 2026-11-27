"""identity.roles, permissions, role_permissions, role_grants; the B1 seed (05 §C.6).

Revision ID: b01_08
Revises: b01_07

The seed is a frozen copy: later builds add roles and permissions in their own revisions.
The permission-code CHECK accepts single-word codes (``moderation``, ``privacy``,
``curriculum``) that 05 §C.6 and 14 §3 use; 01's regex required a dot.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b01_08"
down_revision = "b01_07"
branch_labels = None
depends_on = None

S = "identity"
TSTZ = sa.DateTime(timezone=True)
SCOPES = "'global', 'track', 'subject', 'tenant', 'batch'"
PERMISSIONS = [
    ("user.read", "Look up users", "AUTH"),
    ("user.write", "Suspend or reinstate users", "AUTH"),
    ("role.grant", "Grant and revoke roles", "AUTH"),
    ("audit.read", "Search the audit log", "OPS"),
    ("ops.config", "Change runtime config and kill switches", "OPS"),
    ("moderation", "Moderate reports, restrictions and terms", "COM"),
    ("privacy", "Handle export and deletion requests", "AUTH"),
    ("content.read", "Read content in the CMS", "CMS"),
    ("content.author", "Author questions and content", "CMS"),
    ("content.verify", "Verify answer keys", "CMS"),
    ("content.publish", "Publish content", "CMS"),
    ("content.triage", "Triage content reports", "CMS"),
    ("content.lead", "Lead a content team", "CMS"),
    ("content.exam", "Prepare exam papers", "CMS"),
    ("curriculum", "Manage tracks, syllabi and taxonomy", "TAX"),
]
ROLES = [
    ("student", "শিক্ষার্থী", "Student", False),
    ("parent", "অভিভাবক", "Parent", False),
    ("teacher", "শিক্ষক", "Teacher", False),
    ("institution_admin", "প্রতিষ্ঠান অ্যাডমিন", "Institution admin", False),
    ("content_author", "কনটেন্ট লেখক", "Content author", True),
    ("reviewer", "রিভিউয়ার", "Reviewer", True),
    ("ops_admin", "অপারেশনস অ্যাডমিন", "Operations admin", True),
    ("super_admin", "সুপার অ্যাডমিন", "Super admin", True),
]
ROLE_PERMISSIONS = {
    "content_author": ["content.read", "content.author"],
    "reviewer": ["content.read", "content.verify", "content.triage"],
    "ops_admin": ["user.read", "user.write", "audit.read", "ops.config", "moderation", "privacy"],
    "super_admin": [code for code, _, _ in PERMISSIONS],
}


def upgrade() -> None:
    roles = op.create_table(
        "roles",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("name_bn", sa.Text, nullable=False),
        sa.Column("name_en", sa.Text, nullable=False),
        sa.Column("is_staff", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.CheckConstraint("code ~ '^[a-z_]+$'", name="code"),
        schema=S,
    )
    permissions = op.create_table(
        "permissions",
        sa.Column("code", sa.Text, primary_key=True),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("module", sa.Text, nullable=False),
        sa.CheckConstraint("code ~ '^[a-z_]+(\\.[a-z_]+)*$'", name="code"),
        schema=S,
    )
    links = op.create_table(
        "role_permissions",
        sa.Column("role_code", sa.Text, sa.ForeignKey("identity.roles.code"), primary_key=True),
        sa.Column(
            "permission_code", sa.Text, sa.ForeignKey("identity.permissions.code"), primary_key=True
        ),
        schema=S,
    )
    users = "identity.users.id"
    op.create_table(
        "role_grants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", UUID(as_uuid=True), sa.ForeignKey(users, ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("role_code", sa.Text, sa.ForeignKey("identity.roles.code"), nullable=False),
        sa.Column("scope_type", sa.Text, nullable=False, server_default="global"),
        sa.Column("scope_id", UUID(as_uuid=True)),
        sa.Column("granted_by", UUID(as_uuid=True), sa.ForeignKey(users, ondelete="RESTRICT")),
        sa.Column("granted_at", TSTZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", TSTZ),
        sa.CheckConstraint(f"scope_type IN ({SCOPES})", name="scope_type"),
        sa.CheckConstraint("(scope_type = 'global') = (scope_id IS NULL)", name="scope_id"),
        schema=S,
    )
    op.create_index(
        "uq_role_grants_active",
        "role_grants",
        ["user_id", "role_code", "scope_type", "scope_id"],
        unique=True,
        schema=S,
        postgresql_where=sa.text("revoked_at IS NULL"),
        postgresql_nulls_not_distinct=True,  # one active global grant per role
    )
    op.create_index(
        "ix_role_grants_scope_type_scope_id",
        "role_grants",
        ["scope_type", "scope_id"],
        schema=S,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.bulk_insert(
        roles,
        [dict(zip(("code", "name_bn", "name_en", "is_staff"), r, strict=True)) for r in ROLES],
    )
    op.bulk_insert(
        permissions,
        [{"code": c, "description": d, "module": m} for c, d, m in PERMISSIONS],
    )
    op.bulk_insert(
        links,
        [
            {"role_code": r, "permission_code": p}
            for r, codes in ROLE_PERMISSIONS.items()
            for p in codes
        ],
    )


def downgrade() -> None:
    op.drop_table("role_grants", schema=S)
    op.drop_table("role_permissions", schema=S)
    op.drop_table("permissions", schema=S)
    op.drop_table("roles", schema=S)

"""Roles and permission codes created in B1 (05 §C.6). Later builds add theirs in migrations.

``b01_08`` seeds a frozen copy of these lists; ``tests/contract/test_rbac_seed.py`` checks
that the database at head and this file agree.
"""

from __future__ import annotations

from typing import Final

USER_READ: Final = "user.read"
USER_WRITE: Final = "user.write"
ROLE_GRANT: Final = "role.grant"
AUDIT_READ: Final = "audit.read"
OPS_CONFIG: Final = "ops.config"
MODERATION: Final = "moderation"
PRIVACY: Final = "privacy"
CONTENT_READ: Final = "content.read"
CONTENT_AUTHOR: Final = "content.author"
CONTENT_VERIFY: Final = "content.verify"
CONTENT_PUBLISH: Final = "content.publish"
CONTENT_TRIAGE: Final = "content.triage"
CONTENT_LEAD: Final = "content.lead"
CONTENT_EXAM: Final = "content.exam"
CURRICULUM: Final = "curriculum"

# code -> (description, owning module)
PERMISSIONS: Final[dict[str, tuple[str, str]]] = {
    USER_READ: ("Look up users", "AUTH"),
    USER_WRITE: ("Suspend or reinstate users", "AUTH"),
    ROLE_GRANT: ("Grant and revoke roles", "AUTH"),
    AUDIT_READ: ("Search the audit log", "OPS"),
    OPS_CONFIG: ("Change runtime config and kill switches", "OPS"),
    MODERATION: ("Moderate reports, restrictions and terms", "COM"),
    PRIVACY: ("Handle export and deletion requests", "AUTH"),
    CONTENT_READ: ("Read content in the CMS", "CMS"),
    CONTENT_AUTHOR: ("Author questions and content", "CMS"),
    CONTENT_VERIFY: ("Verify answer keys", "CMS"),
    CONTENT_PUBLISH: ("Publish content", "CMS"),
    CONTENT_TRIAGE: ("Triage content reports", "CMS"),
    CONTENT_LEAD: ("Lead a content team", "CMS"),
    CONTENT_EXAM: ("Prepare exam papers", "CMS"),
    CURRICULUM: ("Manage tracks, syllabi and taxonomy", "TAX"),
}

# code -> (name_bn, name_en, is_staff)
ROLES: Final[dict[str, tuple[str, str, bool]]] = {
    "student": ("শিক্ষার্থী", "Student", False),
    "parent": ("অভিভাবক", "Parent", False),
    "teacher": ("শিক্ষক", "Teacher", False),
    "institution_admin": ("প্রতিষ্ঠান অ্যাডমিন", "Institution admin", False),
    "content_author": ("কনটেন্ট লেখক", "Content author", True),
    "reviewer": ("রিভিউয়ার", "Reviewer", True),
    "ops_admin": ("অপারেশনস অ্যাডমিন", "Operations admin", True),
    "super_admin": ("সুপার অ্যাডমিন", "Super admin", True),
}

ROLE_PERMISSIONS: Final[dict[str, tuple[str, ...]]] = {
    "content_author": (CONTENT_READ, CONTENT_AUTHOR),
    "reviewer": (CONTENT_READ, CONTENT_VERIFY, CONTENT_TRIAGE),
    "ops_admin": (USER_READ, USER_WRITE, AUDIT_READ, OPS_CONFIG, MODERATION, PRIVACY),
    "super_admin": tuple(PERMISSIONS),
}

STAFF_ROLES: Final = frozenset(code for code, (_, _, staff) in ROLES.items() if staff)
DEFAULT_ROLE: Final = "student"

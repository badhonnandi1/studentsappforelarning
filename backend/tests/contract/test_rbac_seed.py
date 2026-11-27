"""The ``b01_08`` seed at head equals ``auth/internal/permissions.py`` (05 §C.6)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal import permissions as p
from app.modules.auth.internal.models import Permission, Role, RolePermission

pytestmark = [pytest.mark.contract, pytest.mark.db]


async def test_roles_permissions_and_links_match(session: AsyncSession) -> None:
    roles = (await session.execute(select(Role))).scalars().all()
    assert {r.code: (r.name_bn, r.name_en, r.is_staff) for r in roles} == p.ROLES
    perms = (await session.execute(select(Permission))).scalars().all()
    assert {x.code: (x.description, x.module) for x in perms} == p.PERMISSIONS
    links = (await session.execute(select(RolePermission))).scalars().all()
    seeded: dict[str, set[str]] = {}
    for link in links:
        seeded.setdefault(link.role_code, set()).add(link.permission_code)
    assert seeded == {role: set(codes) for role, codes in p.ROLE_PERMISSIONS.items()}
    assert len(p.ROLES) == 8
    assert {"content_author", "reviewer", "ops_admin", "super_admin"} == p.STAFF_ROLES

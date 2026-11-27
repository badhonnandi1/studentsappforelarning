"""Role grants and the permissions they carry."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.actor import Grant
from app.modules.auth.internal.models import Role, RoleGrant, RolePermission


async def grants_for(session: AsyncSession, user_id: uuid.UUID) -> list[Grant]:
    """One ``Grant`` per (permission, scope) of the user's active role grants."""
    stmt = (
        select(RolePermission.permission_code, RoleGrant.scope_type, RoleGrant.scope_id)
        .join(RoleGrant, RoleGrant.role_code == RolePermission.role_code)
        .where(RoleGrant.user_id == user_id, RoleGrant.revoked_at.is_(None))
        .distinct()
        .order_by(RolePermission.permission_code, RoleGrant.scope_type)
    )
    return [Grant(p, t, s) for p, t, s in (await session.execute(stmt)).all()]


async def role(session: AsyncSession, code: str) -> Role | None:
    return await session.get(Role, code)


async def role_permissions(session: AsyncSession, code: str) -> frozenset[str]:
    stmt = select(RolePermission.permission_code).where(RolePermission.role_code == code)
    return frozenset((await session.execute(stmt)).scalars())


async def active_duplicate(
    session: AsyncSession,
    user_id: uuid.UUID,
    role_code: str,
    scope_type: str,
    scope_id: uuid.UUID | None,
) -> RoleGrant | None:
    stmt = select(RoleGrant).where(
        RoleGrant.user_id == user_id,
        RoleGrant.role_code == role_code,
        RoleGrant.scope_type == scope_type,
        RoleGrant.scope_id.is_(None) if scope_id is None else RoleGrant.scope_id == scope_id,
        RoleGrant.revoked_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_grant(session: AsyncSession, grant_id: uuid.UUID) -> RoleGrant | None:
    return await session.get(RoleGrant, grant_id, with_for_update=True, populate_existing=True)


async def add(session: AsyncSession, grant: RoleGrant) -> None:
    session.add(grant)
    await session.flush()

"""Plain factory functions for ``identity`` rows (05 §C.9: no factory-boy)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.core.security.crypto import encrypt_field
from app.core.security.hashing import keyed_hash
from app.modules.auth.internal.models import RoleGrant, User


async def make_user(
    session: AsyncSession,
    user_id: uuid.UUID | None = None,
    *,
    phone: str | None = None,
    date_of_birth: date | None = date(2008, 1, 1),
    **fields: Any,
) -> User:
    user = User(id=user_id or uuid7(), date_of_birth=date_of_birth, **fields)
    if phone is not None:
        user.phone_hash = keyed_hash(phone, "phone")
        user.phone_enc = encrypt_field(phone, "identity.users.phone")
    session.add(user)
    await session.flush()
    return user


async def grant_role(
    session: AsyncSession, user_id: uuid.UUID, role: str, **fields: Any
) -> RoleGrant:
    row = RoleGrant(id=uuid7(), user_id=user_id, role_code=role, **fields)
    session.add(row)
    await session.flush()
    return row

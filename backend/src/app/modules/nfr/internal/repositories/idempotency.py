"""``platform.idempotency_keys`` SQL."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nfr.internal.models import IdempotencyKey


async def get(session: AsyncSession, user_id: uuid.UUID, key: uuid.UUID) -> IdempotencyKey | None:
    return await session.get(IdempotencyKey, (user_id, key), populate_existing=True)


async def store_response(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    key: uuid.UUID,
    request_hash: bytes,
    method: str,
    route: str,
    status_code: int,
    response: Any | None,
    resource_id: uuid.UUID | None,
) -> bool:
    """Insert the completed record; return False if a row already existed (lost a race)."""
    stmt = (
        insert(IdempotencyKey)
        .values(
            user_id=user_id,
            key=key,
            request_hash=request_hash,
            method=method,
            route=route,
            status_code=status_code,
            response=response,
            resource_id=resource_id,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
        .returning(IdempotencyKey.key)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None

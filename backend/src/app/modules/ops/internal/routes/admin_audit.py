"""``GET /v1/admin/audit-log`` and ``PUT /v1/admin/runtime-config/{key}`` (05 §D)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.pagination import DEFAULT_LIMIT, Limit, Page
from app.core.security.actor import Actor
from app.core.security.deps import staff_permission
from app.modules.ops.internal.repositories.audit import AuditFilters
from app.modules.ops.internal.schemas.audit import (
    AuditEntryOut,
    RuntimeConfigIn,
    RuntimeConfigOut,
)
from app.modules.ops.internal.services import audit_search, runtime_config_admin

router = APIRouter(prefix="/v1/admin", tags=["admin"])
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]


@router.get("/audit-log", response_model=Page[AuditEntryOut])
async def audit_log(
    _actor: Annotated[Actor, Depends(staff_permission("audit.read"))],
    session: Session,
    clock: Now,
    actor_user_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    action: str | None = None,
    start: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    end: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    cursor: str | None = None,
    limit: Limit = DEFAULT_LIMIT,
) -> Page[AuditEntryOut]:
    begin, finish = audit_search.time_range(start, end, clock.now())
    filters = AuditFilters(begin, finish, actor_user_id, target_type, target_id, action)
    rows, next_cursor = await audit_search.search(session, filters, cursor, limit)
    return Page[AuditEntryOut](
        items=[AuditEntryOut.model_validate(r) for r in rows], next_cursor=next_cursor
    )


@router.put("/runtime-config/{key}", response_model=RuntimeConfigOut)
async def put_runtime_config(
    key: str,
    body: RuntimeConfigIn,
    actor: Annotated[Actor, Depends(staff_permission("ops.config"))],
    session: Session,
    clock: Now,
) -> RuntimeConfigOut:
    now = clock.now()
    value = await runtime_config_admin.update(session, actor, key, body.value, body.reason, now)
    return RuntimeConfigOut(key=key, value=value, updated_at=now)

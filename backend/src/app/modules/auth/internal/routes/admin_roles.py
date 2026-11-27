"""``POST /v1/admin/role-grants`` and ``DELETE /v1/admin/role-grants/{id}`` (05 §D)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, get_clock
from app.core.db import get_session
from app.core.security.actor import Actor
from app.core.security.deps import staff_permission
from app.modules.auth.internal.permissions import ROLE_GRANT
from app.modules.auth.internal.schemas.rbac import RoleGrantIn, RoleGrantOut
from app.modules.auth.internal.services import rbac

router = APIRouter(prefix="/v1/admin/role-grants", tags=["admin"])
Granter = Annotated[Actor, Depends(staff_permission(ROLE_GRANT))]
Session = Annotated[AsyncSession, Depends(get_session)]
Now = Annotated[Clock, Depends(get_clock)]


@router.post("", status_code=201, response_model=RoleGrantOut)
async def create_grant(
    body: RoleGrantIn, actor: Granter, session: Session, clock: Now
) -> RoleGrantOut:
    row = await rbac.grant(session, actor, body, clock.now())
    return RoleGrantOut.model_validate(row)


@router.delete("/{grant_id}", status_code=204)
async def delete_grant(
    grant_id: uuid.UUID, actor: Granter, session: Session, clock: Now
) -> Response:
    await rbac.revoke(session, actor, grant_id, clock.now())
    return Response(status_code=204)

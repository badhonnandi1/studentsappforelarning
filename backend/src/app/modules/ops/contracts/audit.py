"""Audit DTOs other modules pass to ``ops.audited``."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.security.actor import Actor

ActorKind = Literal["staff", "user", "system", "provider"]


class AuditTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str = Field(pattern=r"^[a-z_]+$")
    id: str = Field(min_length=1, max_length=200)


class AuditActor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ActorKind
    user_id: uuid.UUID | None = None
    roles: tuple[str, ...] = ()
    tenant_id: uuid.UUID | None = None

    @classmethod
    def of(cls, actor: Actor) -> AuditActor:
        """Staff for admin-audience tokens, otherwise the signed-in user."""
        kind: ActorKind = "staff" if actor.audience == "admin" else "user"
        return cls(kind=kind, user_id=actor.user_id, roles=tuple(sorted(actor.roles)))

    @classmethod
    def system(cls) -> AuditActor:
        return cls(kind="system")

    @classmethod
    def provider(cls) -> AuditActor:
        return cls(kind="provider")

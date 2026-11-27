"""Admin role grants (05 §D ``/v1/admin/role-grants``)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

ScopeType = Literal["global", "subject", "tenant"]


class RoleGrantIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: uuid.UUID
    role_code: str = Field(pattern=r"^[a-z_]{1,40}$")
    scope_type: ScopeType = "global"
    scope_id: uuid.UUID | None = None
    reason: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def scope_matches(self) -> Self:
        if (self.scope_type == "global") != (self.scope_id is None):
            raise ValueError("scope_id is required for subject and tenant scopes, and only then")
        return self


class RoleGrantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    role_code: str
    scope_type: ScopeType
    scope_id: uuid.UUID | None
    granted_by: uuid.UUID | None
    granted_at: datetime

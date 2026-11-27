"""What ``com.moderate`` returns, and the hook AUTH implements so a ban can end sessions."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

Verdict = Literal["allow", "flag", "block"]
Context = Literal[
    "display_name", "profile_photo", "error_report", "ticket", "tutor_input", "tutor_output",
    "post", "group_message", "content_report",
]  # fmt: skip
Scope = Literal["global", "community", "tutor", "display_name", "profile"]


class ModerationVerdict(BaseModel):
    """``block`` for severity 2–3; ``alert`` marks severity 3 (block and alert)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Verdict
    terms: tuple[str, ...] = ()
    score: float | None = None
    alert: bool = False


class SessionRevoker(Protocol):
    """Implemented by AUTH (COM must not import it, 04 §4 rule 4)."""

    async def revoke_all(
        self, session: AsyncSession, user_id: uuid.UUID, now: datetime
    ) -> list[uuid.UUID]: ...

    async def after_commit(self, session_ids: Sequence[uuid.UUID]) -> None: ...

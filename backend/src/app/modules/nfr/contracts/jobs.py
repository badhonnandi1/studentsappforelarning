"""What a job handler receives. Handlers run inside the job's transaction."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class JobContext:
    job_id: uuid.UUID
    kind: str
    queue: str
    attempt: int  # 1 on the first run
    session: AsyncSession  # already in a transaction; do not commit
    now: datetime


JobHandler = Callable[[JobContext, dict[str, Any]], Awaitable[None]]

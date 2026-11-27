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
DeadJobHook = Callable[[AsyncSession, dict[str, Any], str], Awaitable[None]]


@dataclass(frozen=True)
class DeadLetterAware:
    """A handler with a hook the worker calls, in a new transaction, when the job goes dead.

    The failing attempt's own transaction has rolled back, so this is where a handler records
    the final outcome (for example an SMS marked ``failed``).
    """

    run: JobHandler
    on_dead: DeadJobHook

    async def __call__(self, ctx: JobContext, payload: dict[str, Any]) -> None:
        await self.run(ctx, payload)

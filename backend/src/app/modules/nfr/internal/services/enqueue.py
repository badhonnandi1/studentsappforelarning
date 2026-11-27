"""``enqueue``: add a job in the caller's transaction."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs.queues import PRIORITY_MAX, PRIORITY_MIN, QUEUES
from app.modules.nfr.internal.repositories.jobs import NewJob, insert_job


async def enqueue(
    session: AsyncSession,
    kind: str,
    payload: dict[str, Any],
    *,
    now: datetime,
    queue: str = "default",
    run_at: datetime | None = None,
    priority: int = 0,
    dedupe_key: str | None = None,
    dedupe_until: datetime | None = None,
    max_attempts: int = 8,
) -> uuid.UUID | None:
    """Return the job id, or None when a job with the same ``dedupe_key`` already exists."""
    if queue not in QUEUES:
        raise ValueError(f"unknown queue {queue!r}; queues are defined in core/jobs/queues.py")
    if not PRIORITY_MIN <= priority <= PRIORITY_MAX:
        raise ValueError(f"priority must be within {PRIORITY_MIN}..{PRIORITY_MAX}")
    if dedupe_until is not None and dedupe_key is None:
        raise ValueError("dedupe_until needs a dedupe_key")
    job = NewJob(
        kind=kind,
        payload=payload,
        queue=queue,
        priority=priority,
        run_at=run_at,
        dedupe_key=dedupe_key,
        dedupe_until=dedupe_until,
        max_attempts=max_attempts,
    )
    return await insert_job(session, job, now)

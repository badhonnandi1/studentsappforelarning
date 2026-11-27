"""``platform.jobs`` SQL: insert with dedupe, SKIP LOCKED claim, complete, retry, dead-letter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import uuid7
from app.modules.nfr.internal.models import DeadJob, Job

MAX_ERROR = 4096


@dataclass(frozen=True)
class NewJob:
    kind: str
    payload: dict[str, Any]
    queue: str = "default"
    priority: int = 0
    run_at: datetime | None = None
    dedupe_key: str | None = None
    dedupe_until: datetime | None = None
    max_attempts: int = 8


async def insert_job(session: AsyncSession, job: NewJob, now: datetime) -> uuid.UUID | None:
    """Return the new id, or None when an existing row holds the same ``dedupe_key``."""
    stmt = (
        insert(Job)
        .values(
            id=uuid7(),
            kind=job.kind,
            queue=job.queue,
            priority=job.priority,
            payload=job.payload,
            run_at=job.run_at or now,
            dedupe_key=job.dedupe_key,
            dedupe_until=job.dedupe_until,
            max_attempts=job.max_attempts,
        )
        .on_conflict_do_nothing(
            index_elements=["dedupe_key"], index_where=text("dedupe_key IS NOT NULL")
        )
        .returning(Job.id)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


_CLAIM = text("""
WITH picked AS (
    SELECT id FROM platform.jobs
    WHERE status = 'queued' AND queue = ANY(:queues) AND run_at <= :now
    ORDER BY priority DESC, run_at
    LIMIT :n
    FOR UPDATE SKIP LOCKED
)
UPDATE platform.jobs j
SET status = 'running', locked_by = :worker, locked_until = :until, attempts = j.attempts + 1
FROM picked WHERE j.id = picked.id
RETURNING j.id
""")


async def claim_jobs(
    session: AsyncSession, queues: list[str], n: int, worker: str, now: datetime, lease: timedelta
) -> list[Job]:
    params = {"queues": queues, "n": n, "worker": worker, "now": now, "until": now + lease}
    ids = list((await session.execute(_CLAIM, params)).scalars())
    if not ids:
        return []
    rows = await session.execute(
        select(Job).where(Job.id.in_(ids)).order_by(Job.priority.desc(), Job.run_at)
    )
    return list(rows.scalars())


async def renew_leases(
    session: AsyncSession, ids: list[uuid.UUID], worker: str, until: datetime
) -> int:
    stmt = (
        update(Job)
        .where(Job.id.in_(ids), Job.locked_by == worker, Job.status == "running")
        .values(locked_until=until)
    )
    return (await session.execute(stmt)).rowcount  # type: ignore[attr-defined, no-any-return]


async def complete(session: AsyncSession, job: Job, now: datetime) -> None:
    """Unkeyed jobs are deleted; keyed ones stay ``done`` until ``dedupe_until`` (R-18)."""
    if job.dedupe_key is None or job.dedupe_until is None or job.dedupe_until <= now:
        await session.execute(delete(Job).where(Job.id == job.id))
        return
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(status="done", locked_by=None, locked_until=None, last_error=None)
    )


async def move_to_dead(session: AsyncSession, job: Job, error: str) -> None:
    session.add(
        DeadJob(
            id=uuid7(),
            original_job_id=job.id,
            kind=job.kind,
            queue=job.queue,
            payload=job.payload,
            attempts=job.attempts,
            last_error=error[:MAX_ERROR],
        )
    )
    await session.execute(delete(Job).where(Job.id == job.id))


async def fail_or_retry(session: AsyncSession, job: Job, error: str, retry_at: datetime) -> bool:
    """Return True when the job was dead-lettered (attempts exhausted)."""
    if job.attempts >= job.max_attempts:
        await move_to_dead(session, job, error)
        return True
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(
            status="queued",
            run_at=retry_at,
            locked_by=None,
            locked_until=None,
            last_error=error[:MAX_ERROR],
        )
    )
    return False


async def expired_leases(session: AsyncSession, now: datetime, limit: int = 100) -> list[Job]:
    """Running jobs whose worker died (lease passed), locked so one recoverer handles each."""
    stmt = (
        select(Job)
        .where(Job.status == "running", Job.locked_until < now)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list((await session.execute(stmt)).scalars())


async def requeue(session: AsyncSession, job: Job) -> None:
    await session.execute(
        update(Job)
        .where(Job.id == job.id)
        .values(status="queued", locked_by=None, locked_until=None, last_error="lease expired")
    )

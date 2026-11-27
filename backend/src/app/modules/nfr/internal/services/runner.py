"""Worker loop: claim → dispatch → commit, with leases, retries and dead-lettering (C.7).

Each job runs in its own transaction together with its completion, so a job's writes and its
removal from the queue commit or roll back as one. A crashed worker's jobs come back when their
lease expires. Up to 8 attempts with ``5 s * 2^n ± 20%`` backoff, then ``dead_jobs``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import Clock, SystemClock
from app.core.resilience import backoff_delay
from app.core.telemetry import counter, histogram
from app.modules.nfr.contracts.jobs import JobContext, JobHandler
from app.modules.nfr.internal.models import Job
from app.modules.nfr.internal.repositories import jobs as repo

log = structlog.get_logger(__name__)
SessionFactory = Callable[[], AsyncSession]


@dataclass(frozen=True)
class WorkerConfig:
    queues: tuple[str, ...]
    batch: int = 10
    lease: timedelta = timedelta(seconds=60)
    renew_every_s: float = 20.0
    busy_poll_s: float = 0.2
    idle_poll_s: float = 1.0
    recover_every_s: float = 10.0
    backoff_base_s: float = 5.0
    backoff_cap_s: float = 3600.0


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class Worker:
    def __init__(
        self,
        sessions: SessionFactory,
        handlers: Mapping[str, JobHandler],
        config: WorkerConfig,
        *,
        clock: Clock | None = None,
        worker_id: str | None = None,
    ) -> None:
        self.sessions, self.handlers, self.config = sessions, dict(handlers), config
        self.clock = clock or SystemClock()
        self.worker_id = worker_id or default_worker_id()
        self.in_flight: set[Job] = set()
        self._last_recover = float("-inf")

    async def recover(self) -> int:
        """Requeue jobs whose lease expired; dead-letter them when attempts are exhausted."""
        now = self.clock.now()
        async with self.sessions() as session, session.begin():
            expired = await repo.expired_leases(session, now)
            for job in expired:
                if job.attempts >= job.max_attempts:
                    await repo.move_to_dead(session, job, "lease expired on the last attempt")
                    counter("app_jobs_dead_total").add(1, {"kind": job.kind})
                else:
                    await repo.requeue(session, job)
        if expired:
            log.warning("jobs_lease_recovered", count=len(expired))
        return len(expired)

    async def claim(self) -> list[Job]:
        now = self.clock.now()
        async with self.sessions() as session, session.begin():
            return await repo.claim_jobs(
                session,
                list(self.config.queues),
                self.config.batch,
                self.worker_id,
                now,
                self.config.lease,
            )

    async def execute(self, job: Job) -> bool:
        """Run one claimed job. Return True on success."""
        started = time.perf_counter()
        handler = self.handlers.get(job.kind)
        try:
            if handler is None:
                raise LookupError(f"no handler registered for job kind {job.kind}")
            async with self.sessions() as session, session.begin():
                now = self.clock.now()
                ctx = JobContext(job.id, job.kind, job.queue, job.attempts, session, now)
                await handler(ctx, job.payload)
                await repo.complete(session, job, now)
        except Exception as exc:
            await self._failed(job, f"{type(exc).__name__}: {exc}")
            return False
        finally:
            histogram("app_job_duration_seconds").record(
                time.perf_counter() - started, {"kind": job.kind}
            )
        counter("app_jobs_completed_total").add(1, {"kind": job.kind})
        return True

    async def _failed(self, job: Job, error: str) -> None:
        delay = backoff_delay(
            job.attempts - 1, base_s=self.config.backoff_base_s, cap_s=self.config.backoff_cap_s
        )
        retry_at = self.clock.now() + timedelta(seconds=delay)
        async with self.sessions() as session, session.begin():
            dead = await repo.fail_or_retry(session, job, error, retry_at)
        if dead:
            counter("app_jobs_dead_total").add(1, {"kind": job.kind})
            log.error("job_dead", kind=job.kind, job_id=str(job.id), attempts=job.attempts)
            await self._on_dead(job, error)
        else:
            log.warning("job_retry", kind=job.kind, job_id=str(job.id), attempt=job.attempts)

    async def _on_dead(self, job: Job, error: str) -> None:
        hook = getattr(self.handlers.get(job.kind), "on_dead", None)
        if hook is None:
            return
        try:
            async with self.sessions() as session, session.begin():
                await hook(session, job.payload, error)
        except Exception:
            log.exception("job_dead_hook_failed", kind=job.kind, job_id=str(job.id))

    async def renew(self) -> int:
        if not self.in_flight:
            return 0
        until = self.clock.now() + self.config.lease
        async with self.sessions() as session, session.begin():
            ids = [job.id for job in self.in_flight]
            return await repo.renew_leases(session, ids, self.worker_id, until)

    async def run_once(self) -> int:
        """Recover (throttled), claim one batch and run it. Return the number of jobs run."""
        if time.monotonic() - self._last_recover >= self.config.recover_every_s:
            self._last_recover = time.monotonic()
            await self.recover()
        claimed = await self.claim()
        self.in_flight.update(claimed)
        try:
            await asyncio.gather(*(self.execute(job) for job in claimed))
        finally:
            self.in_flight.difference_update(claimed)
        return len(claimed)

    async def _renew_loop(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), self.config.renew_every_s)
            if not stop.is_set():
                try:
                    await self.renew()
                except Exception:
                    log.exception("job_lease_renew_failed")

    async def run(self, stop: asyncio.Event) -> None:
        """Poll until ``stop`` is set; the current batch always finishes (graceful shutdown)."""
        renewer = asyncio.create_task(self._renew_loop(stop))
        log.info("worker_started", worker=self.worker_id, queues=list(self.config.queues))
        try:
            while not stop.is_set():
                try:
                    ran = await self.run_once()
                except Exception:
                    log.exception("worker_iteration_failed")
                    ran = 0
                pause = self.config.busy_poll_s if ran else self.config.idle_poll_s
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), pause)
        finally:
            stop.set()
            await renewer
            log.info("worker_stopped", worker=self.worker_id)

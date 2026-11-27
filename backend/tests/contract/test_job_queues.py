"""Queues, job kinds and periodic jobs agree across code and the database (C.7)."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jobs.queues import QUEUES
from app.entrypoints.workers.main import register_periodic_jobs
from app.modules.nfr.internal.services.consumer import consumers
from app.modules.nfr.internal.services.scheduler import PERIODIC
from app.modules.registry import all_job_handlers

pytestmark = pytest.mark.contract


def test_every_periodic_job_has_a_handler_and_a_known_queue() -> None:
    saved = list(PERIODIC)
    try:
        register_periodic_jobs()
        register_periodic_jobs()  # safe to call twice
        assert "auth.sessions.purge_stale" in {job.kind for job in PERIODIC}
        handlers = all_job_handlers()
        for job in PERIODIC:
            assert job.kind in handlers, job.kind
            assert job.queue in QUEUES, job.queue
    finally:
        PERIODIC[:] = saved


def test_consumers_use_known_queues() -> None:
    assert all(spec.queue in QUEUES for spec in consumers())


def test_job_kinds_are_namespaced() -> None:
    assert all(re.fullmatch(r"[a-z_]+(\.[a-z_]+)+", kind) for kind in all_job_handlers())


@pytest.mark.db
async def test_queue_check_constraint_matches_code(session: AsyncSession) -> None:
    definition = (
        await session.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid = 'platform.jobs'::regclass AND conname = 'ck_jobs_queue'"
            )
        )
    ).scalar_one()
    assert set(re.findall(r"'([a-z_]+)'::text", definition)) == set(QUEUES)

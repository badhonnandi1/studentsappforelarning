"""Postgres job queue for all background work except exam answers (v2 §0.2, C9).

Placeholder: no table yet. Planned shape, in schema ``platform``:

    jobs(id, kind, payload, run_at, attempts, locked_until, ...)
    processed_events(consumer, event_id)   -- dedupe per consumer (v2 §3.5)
    dead_jobs(...)                          -- after 8 tries, with an alert

The ``workers`` deployable claims work with:

    SELECT ... FROM platform.jobs
    WHERE run_at <= now()
    ORDER BY run_at
    FOR UPDATE SKIP LOCKED
    LIMIT :batch

Retries use exponential backoff with jitter. Revisit above ~1,000 jobs/s.
"""

from collections.abc import Callable
from typing import Any

JobHandler = Callable[[dict[str, Any]], None]

# Job kinds planned in v2 §2.1. Handlers register here as modules are built,
# e.g. "outbox.relay", "gam.leaderboard.rebuild", "qb.import", "plan.deliver".
HANDLERS: dict[str, JobHandler] = {}


def claim_next(batch: int = 10) -> list[dict[str, Any]]:
    """Claim due jobs with FOR UPDATE SKIP LOCKED. Not implemented yet."""
    raise NotImplementedError("Job queue is deferred: table platform.jobs comes with NFR work")

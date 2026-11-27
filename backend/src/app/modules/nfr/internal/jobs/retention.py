"""``platform.retention.purge``: batched deletes of expired rows (hourly)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nfr.contracts.jobs import JobContext
from app.modules.nfr.internal.jobs.partition_maintenance import table_exists

log = structlog.get_logger(__name__)
BATCH = 5000
MAX_BATCHES = 20  # per table per run, so one run stays short


@dataclass(frozen=True)
class RetentionRule:
    table: str
    where: str  # SQL predicate over the bound timestamptz parameter :now


RULES: tuple[RetentionRule, ...] = (
    RetentionRule("platform.idempotency_keys", "expires_at < :now"),
    RetentionRule(
        "platform.jobs", "status = 'done' AND dedupe_until IS NOT NULL AND dedupe_until < :now"
    ),
    RetentionRule(
        "platform.dead_jobs",
        "resolved_at IS NOT NULL AND resolved_at < CAST(:now AS timestamptz) - interval '30 days'",
    ),
    RetentionRule(
        "identity.otp_challenges", "created_at < CAST(:now AS timestamptz) - interval '30 days'"
    ),
)


async def purge(
    session: AsyncSession, now: datetime, rules: tuple[RetentionRule, ...] = RULES
) -> dict[str, int]:
    report: dict[str, int] = {}
    for rule in rules:
        if not await table_exists(session, rule.table):
            continue
        sql = text(
            f"DELETE FROM {rule.table} WHERE ctid IN "  # noqa: S608 - table and predicate are constants
            f"(SELECT ctid FROM {rule.table} WHERE {rule.where} LIMIT :batch)"
        )
        total = 0
        for _ in range(MAX_BATCHES):
            deleted = (await session.execute(sql, {"now": now, "batch": BATCH})).rowcount  # type: ignore[attr-defined]
            total += deleted
            if deleted < BATCH:
                break
        report[rule.table] = total
    log.info("retention_purged", report=report)
    return report


async def handle(ctx: JobContext, _payload: dict[str, Any]) -> None:
    await purge(ctx.session, ctx.now)

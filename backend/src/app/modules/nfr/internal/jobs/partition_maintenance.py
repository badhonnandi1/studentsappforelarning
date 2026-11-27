"""``platform.partition.maintain``: create partitions ahead and drop expired ones (01 §1.2).

The list below is the only place partition periods and retention live. Tables from later steps
or builds are skipped until their migration has created them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.nfr.contracts.jobs import JobContext

log = structlog.get_logger(__name__)
Period = Literal["day", "month"]


@dataclass(frozen=True)
class PartitionSpec:
    table: str
    period: Period
    ahead: int
    retain: int | None  # periods to keep; None = keep forever
    droppable: bool


PARTITIONS: tuple[PartitionSpec, ...] = (
    PartitionSpec("platform.outbox", "day", 7, retain=7, droppable=True),
    PartitionSpec("platform.processed_events", "day", 7, retain=14, droppable=True),
    # Audit history: 3 years minimum (D4). Dropping waits for the S3 archive job (B9), and the
    # SQL function refuses anything younger than 36 months regardless.
    PartitionSpec("ops.audit_log", "month", 3, retain=36, droppable=False),
    PartitionSpec("notify.sms_messages", "month", 3, retain=24, droppable=True),
)


def months_before(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 - months
    return date(index // 12, index % 12 + 1, 1)


def cutoff(spec: PartitionSpec, today: date) -> date | None:
    """Partitions whose whole range ends on or before this date are expired."""
    if spec.retain is None:
        return None
    if spec.period == "day":
        return today - timedelta(days=spec.retain)
    return months_before(today, spec.retain)


async def table_exists(session: AsyncSession, table: str) -> bool:
    found = await session.execute(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table})
    return bool(found.scalar_one())


async def maintain(
    session: AsyncSession, today: date, specs: tuple[PartitionSpec, ...] = PARTITIONS
) -> dict[str, dict[str, int]]:
    report: dict[str, dict[str, int]] = {}
    for spec in specs:
        if not await table_exists(session, spec.table):
            continue
        created = await session.execute(
            text("SELECT platform.create_range_partitions(:t, :p, :a, :d)"),
            {"t": spec.table, "p": spec.period, "a": spec.ahead, "d": today},
        )
        dropped = 0
        limit = cutoff(spec, today)
        if spec.droppable and limit is not None:
            result = await session.execute(
                text("SELECT platform.drop_partitions_before(:t, :c)"),
                {"t": spec.table, "c": limit},
            )
            dropped = int(result.scalar_one())
        report[spec.table] = {"created": int(created.scalar_one()), "dropped": dropped}
    log.info("partitions_maintained", report=report)
    return report


async def handle(ctx: JobContext, payload: dict[str, Any]) -> None:
    day = date.fromisoformat(payload["date"]) if "date" in payload else ctx.now.date()
    await maintain(ctx.session, day)

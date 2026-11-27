"""10,000 outbox events reach S3 Parquet with no loss and no duplicates, including a relay that
crashes after writing its object and is replayed (05 §F.1 item 7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.clock import FrozenClock
from app.core.db import make_sessionmaker
from app.core.settings import Settings
from app.core.storage import Storage
from app.modules.nfr import publish
from app.modules.nfr.internal.jobs import relay
from app.modules.nfr.internal.jobs.parquet_writer import read_parquet
from app.modules.nfr.internal.models import OutboxEvent
from tests.modules.nfr.test_events import event

pytestmark = [pytest.mark.concurrency, pytest.mark.integration, pytest.mark.slow]
EVENTS = 10_000


class CrashingSink:
    """Writes every object to S3, then fails the third batch after its write (before commit)."""

    def __init__(self, storage: Storage) -> None:
        self.storage, self.writes, self.keys = storage, 0, set[str]()

    async def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        await self.storage.put_object(bucket, key, body, content_type)
        self.writes += 1
        self.keys.add(key)
        if self.writes == 3:
            raise ConnectionError("relay killed after the S3 write")


async def test_ten_thousand_events_relay_once(committed_engine: AsyncEngine) -> None:
    sessions = make_sessionmaker(committed_engine)
    storage = Storage(Settings(_env_file=None))
    bucket = f"sp-test-relay-{uuid.uuid4().hex[:8]}"
    await storage.ensure_bucket(bucket)
    async with sessions() as session, session.begin():
        published = {str((await publish(session, event())).event_id) for _ in range(EVENTS)}
    sink, clock = CrashingSink(storage), FrozenClock(datetime(2026, 1, 15, tzinfo=UTC))

    relayed = crashes = 0
    while True:
        async with sessions() as session:
            try:
                count = await relay.relay_once(session, sink, bucket, [], clock)
            except ConnectionError:
                crashes += 1
                continue
        if count == 0:
            break
        relayed += count
    assert crashes == 1
    assert relayed == EVENTS
    assert sink.writes == EVENTS // relay.RELAY_BATCH + 1  # one batch written twice
    rows: list[str] = []
    for key in sink.keys:  # the replay reused the crashed batch's key, overwriting it
        rows += read_parquet(await storage.get_object(bucket, key)).column("event_id").to_pylist()
    assert len(rows) == EVENTS
    assert set(rows) == published
    async with sessions() as session:
        unrelayed = select(func.count()).where(OutboxEvent.relayed_at.is_(None))
        assert (await session.execute(unrelayed)).scalar_one() == 0

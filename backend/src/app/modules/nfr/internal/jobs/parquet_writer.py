"""Envelopes → one Parquet object; deterministic object keys (B.4 outbox relay)."""

from __future__ import annotations

import io
import json
from collections.abc import Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from app.modules.nfr.contracts.events import EventEnvelope

_TS = pa.timestamp("us", tz="UTC")
SCHEMA = pa.schema(
    [
        pa.field("event_id", pa.string(), nullable=False),
        pa.field("type", pa.string(), nullable=False),
        pa.field("schema_version", pa.int16(), nullable=False),
        pa.field("occurred_at", _TS, nullable=False),
        pa.field("recorded_at", _TS, nullable=False),
        pa.field("aggregate_type", pa.string(), nullable=False),
        pa.field("aggregate_id", pa.string(), nullable=False),
        pa.field("user_id", pa.string()),
        pa.field("track_enrolment_id", pa.string()),
        pa.field("tenant_id", pa.string()),
        pa.field("payload", pa.string(), nullable=False),  # JSON text, versioned by schema_version
    ]
)


def object_key(events: Sequence[EventEnvelope]) -> str:
    """``events/date=YYYY-MM-DD/hour=HH/relay-<first_id>.parquet``: a rerun of the same batch
    overwrites the same object instead of adding a duplicate."""
    first = events[0]
    at = first.recorded_at
    return f"events/date={at:%Y-%m-%d}/hour={at:%H}/relay-{first.event_id}.parquet"


def _opt(value: object) -> str | None:
    return None if value is None else str(value)


def to_parquet(events: Sequence[EventEnvelope]) -> bytes:
    columns = {
        "event_id": [str(e.event_id) for e in events],
        "type": [e.type for e in events],
        "schema_version": [e.schema_version for e in events],
        "occurred_at": [e.occurred_at for e in events],
        "recorded_at": [e.recorded_at for e in events],
        "aggregate_type": [e.aggregate_type for e in events],
        "aggregate_id": [str(e.aggregate_id) for e in events],
        "user_id": [_opt(e.user_id) for e in events],
        "track_enrolment_id": [_opt(e.track_enrolment_id) for e in events],
        "tenant_id": [_opt(e.tenant_id) for e in events],
        "payload": [json.dumps(e.payload, separators=(",", ":"), sort_keys=True) for e in events],
    }
    table = pa.Table.from_pydict(columns, schema=SCHEMA)
    buffer = io.BytesIO()
    pq.write_table(table, buffer, compression="zstd")
    return buffer.getvalue()


def read_parquet(data: bytes) -> pa.Table:
    return pq.read_table(io.BytesIO(data))

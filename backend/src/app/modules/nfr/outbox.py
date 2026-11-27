"""Transactional outbox (v2 §3.5). Placeholder: no table or relay yet.

A module writes its own state and one ``platform.outbox`` row in the SAME
database transaction, using the session it already holds. The outbox relay
(a job in the ``workers`` deployable) later copies committed rows to the S3
event log and the Postgres job queue and marks them sent. Nothing is published
that was not committed, and nothing committed goes unpublished.

Every event uses the shared envelope in v2 §3.3 (event_id, type, schema_version,
occurred_at, recorded_at, user_id, track_enrolment_id, tenant_id, payload).
"""

from typing import Any


def add_event(session: Any, event_type: str, payload: dict[str, Any]) -> None:
    """Stage an event in the caller's open transaction. Not implemented yet."""
    raise NotImplementedError(
        "Outbox is deferred: table platform.outbox and relay come with NFR work"
    )

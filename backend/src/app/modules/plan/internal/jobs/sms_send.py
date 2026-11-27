"""``plan.sms.send``: decrypt → gateway → status, provider id and cost (05 §C.7).

The row lock and the ``queued`` status make a retried or duplicated job a no-op once the
message is sent. Numbers in the reserved test block are never sent to a gateway (R-31). When
the job goes dead, ``on_dead`` marks the message ``failed`` with the last error.
"""

from __future__ import annotations

import base64
import uuid
from datetime import date
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.crypto import decrypt_field
from app.core.settings import TEST_PHONE_FIRST, TEST_PHONE_LAST
from app.core.telemetry import counter
from app.modules import nfr
from app.modules.plan.internal.providers import gateway
from app.modules.plan.internal.providers.sms_base import SendResult
from app.modules.plan.internal.repositories import sms as repo
from app.modules.plan.internal.services.send import BODY_CONTEXT, PHONE_CONTEXT

log = structlog.get_logger(__name__)
TEST_BLOCK = "test_block"


def is_test_phone(phone: str) -> bool:
    return TEST_PHONE_FIRST <= phone <= TEST_PHONE_LAST and len(phone) == len(TEST_PHONE_FIRST)


def _key(payload: dict[str, Any]) -> tuple[uuid.UUID, date]:
    return uuid.UUID(payload["sms_id"]), date.fromisoformat(payload["created_on"])


async def run(ctx: nfr.JobContext, payload: dict[str, Any]) -> None:
    sms_id, created_on = _key(payload)
    row = await repo.lock(ctx.session, sms_id, created_on)
    if row is None or row.status != "queued":
        return
    phone = decrypt_field(row.to_phone_enc, PHONE_CONTEXT)
    if is_test_phone(phone):
        provider, result = TEST_BLOCK, SendResult(None, 0, status="fake_sent")
    else:
        body = decrypt_field(base64.b64decode(payload["body_enc"]), BODY_CONTEXT)
        sender = gateway()
        provider, result = sender.name, await sender.send(phone, body)
    await repo.mark_sent(
        ctx.session,
        row,
        status=result.status,
        provider=provider,
        provider_msg_id=result.provider_msg_id,
        cost_poisha=result.cost_poisha,
        now=ctx.now,
    )
    counter("app_sms_sent_total").add(1, {"purpose": row.purpose, "provider": provider})
    counter("app_sms_segments_total").add(row.segments, {"purpose": row.purpose})


async def on_dead(session: AsyncSession, payload: dict[str, Any], error: str) -> None:
    sms_id, created_on = _key(payload)
    await repo.mark_failed(session, sms_id, created_on, error)
    counter("app_sms_failed_total").add(1)
    log.error("sms_failed", sms_id=str(sms_id))


handler = nfr.DeadLetterAware(run, on_dead)

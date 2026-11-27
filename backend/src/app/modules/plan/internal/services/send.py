"""``send_sms``: render now, store the log row, enqueue ``plan.sms.send`` in the caller's
transaction. The phone is stored hashed and encrypted; the rendered body (it may hold an OTP)
travels encrypted in the job payload, never in plain text.

OTPs go on the ``sms`` queue at priority 100 with 3 attempts, because a code expires in five
minutes and a late retry is useless. Other purposes default to priority 0 and 8 attempts.
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import get_clock
from app.core.ids import uuid7
from app.core.jobs.queues import OTP_PRIORITY
from app.core.security.crypto import encrypt_field
from app.core.security.hashing import keyed_hash
from app.modules import nfr
from app.modules.plan.internal.models import SmsMessage
from app.modules.plan.internal.providers import gateway
from app.modules.plan.internal.repositories import sms as repo
from app.modules.plan.internal.services import templates
from app.shared.bd_phone import E164

JOB_KIND = "plan.sms.send"
PHONE_CONTEXT = "notify.sms_messages.to_phone"
BODY_CONTEXT = "notify.sms.job_body"
OTP_PURPOSES = frozenset({"otp", "guardian_otp"})
OTP_ATTEMPTS, DEFAULT_ATTEMPTS = 3, 8
Purpose = Literal["otp", "guardian_otp", "receipt", "alert", "report", "campaign"]


async def send_sms(
    session: AsyncSession,
    to_phone: str,
    template_code: str,
    params: Mapping[str, object],
    purpose: Purpose,
    priority: int | None = None,
    *,
    lang: Literal["bn", "en"] = "bn",
    now: datetime | None = None,
) -> uuid.UUID:
    """Return the ``notify.sms_messages`` id (AUTH keeps it on the OTP challenge)."""
    if not E164.fullmatch(to_phone):
        raise ValueError("to_phone must be a normalised +8801XXXXXXXXX number")
    if not session.in_transaction():
        raise RuntimeError("send_sms() needs the caller's transaction")
    body = templates.render(await templates.load(session, template_code, lang), params, lang)
    parts = templates.segments(body)
    if parts > templates.MAX_SEGMENTS:
        raise ValueError(f"message is {parts} segments; the limit is {templates.MAX_SEGMENTS}")
    at = (now or get_clock().now()).astimezone(UTC)
    otp = purpose in OTP_PURPOSES
    row = SmsMessage(
        id=uuid7(),
        created_on=at.date(),
        to_phone_hash=keyed_hash(to_phone, "phone"),
        to_phone_enc=encrypt_field(to_phone, PHONE_CONTEXT),
        template_code=template_code,
        lang=lang,
        segments=parts,
        provider=gateway().name,
        status="queued",
        purpose=purpose,
    )
    await repo.insert(session, row)
    payload = {
        "sms_id": str(row.id),
        "created_on": row.created_on.isoformat(),
        "body_enc": base64.b64encode(encrypt_field(body, BODY_CONTEXT)).decode(),
    }
    await nfr.enqueue(
        session,
        JOB_KIND,
        payload,
        now=at,
        queue="sms",
        priority=priority if priority is not None else (OTP_PRIORITY if otp else 0),
        max_attempts=OTP_ATTEMPTS if otp else DEFAULT_ATTEMPTS,
    )
    return row.id

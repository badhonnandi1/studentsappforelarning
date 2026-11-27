"""``notify.sms_messages`` and ``notify.templates`` SQL."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.plan.internal.models import SmsMessage, Template


async def insert(session: AsyncSession, row: SmsMessage) -> None:
    session.add(row)
    await session.flush()


async def lock(session: AsyncSession, sms_id: uuid.UUID, created_on: date) -> SmsMessage | None:
    stmt = (
        select(SmsMessage)
        .where(SmsMessage.id == sms_id, SmsMessage.created_on == created_on)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def mark_sent(
    session: AsyncSession,
    row: SmsMessage,
    *,
    status: str,
    provider: str,
    provider_msg_id: str | None,
    cost_poisha: int | None,
    now: datetime,
) -> None:
    row.status, row.provider, row.provider_msg_id = status, provider, provider_msg_id
    row.cost_poisha, row.sent_at, row.error = cost_poisha, now, None
    await session.flush()


async def mark_failed(
    session: AsyncSession, sms_id: uuid.UUID, created_on: date, error: str
) -> None:
    await session.execute(
        update(SmsMessage)
        .where(
            SmsMessage.id == sms_id,
            SmsMessage.created_on == created_on,
            SmsMessage.status == "queued",
        )
        .values(status="failed", error=error[:500])
    )


async def get_template(session: AsyncSession, code: str, lang: str, channel: str) -> str | None:
    stmt = select(Template.body).where(
        Template.code == code, Template.lang == lang, Template.channel == channel
    )
    return (await session.execute(stmt)).scalar_one_or_none()

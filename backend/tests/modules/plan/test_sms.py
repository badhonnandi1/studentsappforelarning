"""Templates, segments, ``send_sms`` and the ``plan.sms.send`` job through a real worker."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security.hashing import keyed_hash
from app.modules import plan
from app.modules.nfr import JobContext
from app.modules.nfr.internal.models import DeadJob, Job
from app.modules.nfr.internal.services.runner import Worker, WorkerConfig
from app.modules.plan.internal.models import SmsMessage, Template
from app.modules.plan.internal.providers.sms_base import SmsGatewayError
from app.modules.plan.internal.providers.sms_fake import FakeSmsGateway
from app.modules.plan.internal.services import templates
from app.modules.plan.internal.services.templates import render, segments

pytestmark = pytest.mark.db
PHONE = "+8801712345678"
Factory = Callable[[], AsyncSession]


def test_render_bangla_numerals() -> None:
    body = "{name}: {count} টি প্রশ্ন, কোড {code}"
    assert render(body, {"name": "রাফি", "count": 25, "code": "123456"}, "bn") == (
        "রাফি: ২৫ টি প্রশ্ন, কোড 123456"
    )
    assert render("{count} left", {"count": 25}, "en") == "25 left"
    assert render("{flag}", {"flag": True}, "bn") == "True"
    with pytest.raises(ValueError, match="'code' is missing"):
        render("code {code}", {}, "en")


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("", 1),
        ("a" * 160, 1),
        ("a" * 161, 2),
        ("a" * 306, 2),
        ("a" * 307, 3),
        ("€" * 80, 1),  # extension characters count twice
        ("€" * 81, 2),
        ("ক" * 70, 1),
        ("ক" * 71, 2),
        ("ক" * 134, 2),
        ("ক" * 135, 3),
        ("a" * 69 + "😀", 2),  # surrogate pair: 71 UTF-16 code units
    ],
)
def test_segments(text: str, parts: int) -> None:
    assert segments(text) == parts


async def test_seeded_templates_fit_two_segments(session: AsyncSession) -> None:
    rows = (await session.execute(select(Template))).scalars().all()
    assert {(r.code, r.lang) for r in rows} >= {("auth.otp", "bn"), ("auth.guardian_otp", "en")}
    for row in rows:
        assert segments(render(row.body, {"code": "123456"}, row.lang)) <= 2, row.code


def worker(sessions: Factory, clock: FrozenClock) -> Worker:
    config = WorkerConfig(queues=("sms",), recover_every_s=3600)
    return Worker(sessions, plan.job_handlers(), config, clock=clock, worker_id="sms-test")


async def queue_otp(session: AsyncSession, clock: FrozenClock, phone: str = PHONE) -> Any:
    async with session.begin():
        params = {"code": "482913"}
        return await plan.send_sms(session, phone, "auth.otp", params, "otp", now=clock.now())


@pytest.mark.usefixtures("fake_sms")
async def test_send_sms_stores_no_plain_phone(
    session: AsyncSession, now_clock: FrozenClock
) -> None:
    sms_id = await queue_otp(session, now_clock)
    row = (await session.execute(select(SmsMessage))).scalar_one()
    assert row.id == sms_id
    assert (row.status, row.purpose, row.lang, row.segments) == (
        "queued",
        "otp",
        "bn",
        2,
    )  # Bangla is UCS-2: 2 segments
    assert row.to_phone_hash == keyed_hash(PHONE, "phone")
    assert PHONE.encode() not in row.to_phone_enc
    job = (await session.execute(select(Job))).scalar_one()
    assert (job.kind, job.queue, job.priority, job.max_attempts) == ("plan.sms.send", "sms", 100, 3)
    assert "482913" not in str(job.payload)
    assert PHONE not in str(job.payload)


@pytest.mark.usefixtures("fake_sms")
async def test_send_sms_validates(session: AsyncSession, now_clock: FrozenClock) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        await plan.send_sms(session, PHONE, "auth.otp", {"code": "1"}, "otp")
    async with session.begin():
        with pytest.raises(ValueError, match="normalised"):
            await plan.send_sms(session, "01712345678", "auth.otp", {"code": "1"}, "otp")
        with pytest.raises(LookupError, match="no sms template"):
            await plan.send_sms(session, PHONE, "nope", {}, "alert")
        with pytest.raises(ValueError, match="segments"):
            await plan.send_sms(session, PHONE, "auth.otp", {"code": "x" * 2000}, "otp", lang="en")
        await plan.send_sms(session, PHONE, "auth.otp", {"code": "1"}, "receipt", lang="en")
    job = (await session.execute(select(Job))).scalar_one()
    assert (job.priority, job.max_attempts) == (0, 8)


async def test_job_sends_once_via_fake(
    session: AsyncSession, sessions: Factory, now_clock: FrozenClock, fake_sms: FakeSmsGateway
) -> None:
    await queue_otp(session, now_clock)
    assert await worker(sessions, now_clock).run_once() == 1
    assert fake_sms.last_code(PHONE) == "482913"
    assert fake_sms.last_code("+8801812345678") is None
    row = (
        await session.execute(select(SmsMessage).execution_options(populate_existing=True))
    ).scalar_one()
    assert (row.status, row.provider, row.cost_poisha) == ("fake_sent", "fake", 0)
    assert row.provider_msg_id == "fake-1"
    assert row.sent_at == now_clock.now()
    job = plan.job_handlers()["plan.sms.send"]
    payload = {"sms_id": str(row.id), "created_on": row.created_on.isoformat(), "body_enc": ""}
    async with sessions() as again, again.begin():  # a duplicate job finds the message sent
        await job(JobContext(row.id, "plan.sms.send", "sms", 1, again, now_clock.now()), payload)
    assert len(fake_sms.sent) == 1


async def test_test_block_is_never_sent(
    session: AsyncSession, sessions: Factory, now_clock: FrozenClock, fake_sms: FakeSmsGateway
) -> None:
    await queue_otp(session, now_clock, phone="+8801700000042")
    await worker(sessions, now_clock).run_once()
    assert fake_sms.sent == []
    row = (
        await session.execute(select(SmsMessage).execution_options(populate_existing=True))
    ).scalar_one()
    assert (row.status, row.provider) == ("fake_sent", "test_block")


class DownGateway:
    name = "http"
    calls = 0

    async def send(self, to_phone: str, body: str) -> Any:
        assert to_phone
        assert body
        self.calls += 1
        raise SmsGatewayError("sms gateway returned 503")


async def test_gateway_failure_retries_then_dead(
    session: AsyncSession, sessions: Factory, now_clock: FrozenClock, fake_sms: FakeSmsGateway
) -> None:
    del fake_sms
    from app.modules.plan.internal import providers

    down = DownGateway()
    providers.use_gateway(down)
    await queue_otp(session, now_clock)
    w = worker(sessions, now_clock)
    for _ in range(3):
        assert await w.run_once() == 1
        now_clock.advance(timedelta(minutes=5))
    assert down.calls == 3
    dead = (await session.execute(select(DeadJob))).scalar_one()
    assert "503" in dead.last_error
    row = (
        await session.execute(select(SmsMessage).execution_options(populate_existing=True))
    ).scalar_one()
    assert row.status == "failed"
    assert row.error == "SmsGatewayError: sms gateway returned 503"
    assert templates.MAX_TEMPLATE_SEGMENTS == 2

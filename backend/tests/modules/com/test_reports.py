"""``POST /v1/reports`` and the admin queue: create, moderate text, page, resolve (idempotent,
audited, optionally restricting the reported user), rate limit."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.clock import FrozenClock
from app.modules.com.internal.models import ContentReport, UserRestriction
from app.modules.ops.internal.models import AuditLog
from tests.modules.com.conftest import add_terms, as_staff, signed_in
from tests.support.tokens import bearer
from tests.support.users import make_user

pytestmark = [pytest.mark.api, pytest.mark.db, pytest.mark.usefixtures("staff")]
ADMIN = "/v1/admin/moderation/reports"


@pytest.fixture
async def people(session: AsyncSession, clock: FrozenClock) -> tuple[dict[str, str], uuid.UUID]:
    """A signed-in reporter's headers and the reported user's id."""
    async with session.begin():
        reporter, target = await make_user(session), await make_user(session)
    return bearer(await signed_in(session, reporter.id, clock.now())), target.id


@pytest.fixture(autouse=True)
def fresh_tiers() -> Iterator[None]:
    yield
    ratelimit.set_tier_overrides({})


def report_body(target: uuid.UUID, target_type: str = "user", **extra: str) -> dict[str, str]:
    return {"target_type": target_type, "target_id": str(target), "reason": "abuse", **extra}


async def report(client: httpx.AsyncClient, headers: dict[str, str], **body: str) -> str:
    response = await client.post("/v1/reports", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return str(response.json()["report_id"])


async def resolve(
    client: httpx.AsyncClient, report_id: str, key: str | None = None, **body: object
) -> httpx.Response:
    headers = {**as_staff(), "Idempotency-Key": key or str(uuid.uuid4())}
    payload = {"decision": "dismiss", "note": "Checked, nothing wrong", **body}
    return await client.post(f"{ADMIN}/{report_id}:resolve", json=payload, headers=headers)


async def test_create_moderates_text(
    client: httpx.AsyncClient, session: AsyncSession, people: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, target = people
    await add_terms(session, ("en", "badword", 2))
    refused = await client.post(
        "/v1/reports", json=report_body(target, text="you badword"), headers=headers
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "moderation_blocked"
    report_id = await report(client, headers, **report_body(target, text="He keeps insulting me"))
    row = await session.get(ContentReport, uuid.UUID(report_id))
    await session.commit()
    assert row is not None
    assert (row.status, row.text, row.target_id) == ("open", "He keeps insulting me", str(target))
    assert (await client.post("/v1/reports", json=report_body(target))).status_code == 401
    bad = await client.post("/v1/reports", json=report_body(target, "thread"), headers=headers)
    assert bad.status_code == 422


async def test_queue_pages_oldest_first(
    client: httpx.AsyncClient, people: tuple[dict[str, str], uuid.UUID], clock: FrozenClock
) -> None:
    headers, target = people
    ids = []
    for _ in range(3):
        ids.append(await report(client, headers, **report_body(target)))
        clock.advance(seconds=1)
    assert (await resolve(client, ids[1])).status_code == 200
    first = (await client.get(ADMIN, params={"limit": 2}, headers=as_staff())).json()
    assert [r["id"] for r in first["items"]] == ids[:2]
    rest = await client.get(
        ADMIN, params={"limit": 2, "cursor": first["next_cursor"]}, headers=as_staff()
    )
    assert [r["id"] for r in rest.json()["items"]] == ids[2:]
    assert rest.json()["next_cursor"] is None
    open_only = (await client.get(ADMIN, params={"status": "open"}, headers=as_staff())).json()
    assert [r["id"] for r in open_only["items"]] == [ids[0], ids[2]]
    bad = await client.get(ADMIN, params={"cursor": "WyJ4IiwieSJd"}, headers=as_staff())
    assert bad.status_code == 422


async def test_resolve_with_ban_is_idempotent_and_audited(
    client: httpx.AsyncClient, session: AsyncSession, people: tuple[dict[str, str], uuid.UUID],
    clock: FrozenClock,
) -> None:  # fmt: skip
    headers, target = people
    target_token = bearer(await signed_in(session, target, clock.now(), device="device-t001"))
    report_id = await report(client, headers, **report_body(target, "display_name"))
    key = str(uuid.uuid4())
    body = {"decision": "action_taken", "note": "Offensive name", "restriction": {"kind": "ban"}}
    done = await resolve(client, report_id, key, **body)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "actioned"
    replay = await resolve(client, report_id, key, **body)
    assert replay.headers["Idempotent-Replay"] == "true"
    assert replay.json() == done.json()
    assert (await resolve(client, report_id)).status_code == 409
    rows = (await session.execute(select(UserRestriction))).scalars().all()
    actions = (await session.execute(select(AuditLog.action, AuditLog.reason))).all()
    await session.commit()
    assert [(r.user_id, r.kind, r.scope, r.reason) for r in rows] == [
        (target, "ban", "global", "Offensive name")
    ]
    assert ("com.report.resolve", "Offensive name") in [(a[0], a[1]) for a in actions]
    assert ("com.restriction.ban", "Offensive name") in [(a[0], a[1]) for a in actions]
    refused = await client.post("/v1/reports", json=report_body(target), headers=target_token)
    assert refused.status_code == 401


async def test_resolve_rejections(
    client: httpx.AsyncClient, session: AsyncSession, people: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, _target = people
    post_report = await report(client, headers, **report_body(uuid.uuid4(), "post"))
    ghost_report = await report(client, headers, **report_body(uuid.uuid4()))
    mute = {"kind": "mute", "scope": "community"}
    assert (await resolve(client, post_report, restriction=mute)).status_code == 422
    on_post = await resolve(client, post_report, decision="action_taken", restriction=mute)
    assert on_post.status_code == 422
    assert on_post.json()["error"]["details"] == {"restriction": "target_not_a_user"}
    ghost = await resolve(client, ghost_report, decision="action_taken", restriction=mute)
    assert ghost.status_code == 404
    assert (await resolve(client, str(uuid.uuid4()))).status_code == 404
    assert (await resolve(client, post_report, note="no")).status_code == 422
    still_open = (await session.execute(select(ContentReport.status))).scalars().all()
    await session.commit()
    assert still_open == ["open", "open"]


async def test_twenty_reports_per_day(
    client: httpx.AsyncClient, people: tuple[dict[str, str], uuid.UUID]
) -> None:
    headers, target = people
    rule = ratelimit.Rule("user", 2, 86400)
    ratelimit.set_tier_overrides({"report": ratelimit.Tier("report", (rule,))})
    for _ in range(2):
        await report(client, headers, **report_body(target))
    limited = await client.post("/v1/reports", json=report_body(target), headers=headers)
    assert limited.status_code == 429
    assert ratelimit.TIERS["report"].rules == (ratelimit.Rule("user", 20, 86400),)

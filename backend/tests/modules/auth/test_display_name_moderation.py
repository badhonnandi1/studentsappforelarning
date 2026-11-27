"""Display names go through COM moderation on ``PATCH /v1/me`` and at sign-up (step 11)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import User
from app.modules.com.internal.models import ModerationDecision
from app.modules.com.internal.repositories import terms as terms_repo
from tests.modules.auth.conftest import auth_header, send, sign_up, verify
from tests.modules.com.conftest import add_terms

pytestmark = [pytest.mark.api, pytest.mark.db]


@pytest.fixture(autouse=True)
async def terms(session: AsyncSession) -> AsyncIterator[None]:
    await add_terms(session, ("en", "badword", 2), ("en", "spammy", 1))
    yield
    terms_repo.invalidate()


async def decisions(session: AsyncSession) -> list[tuple[str, str]]:
    stmt = select(ModerationDecision.context, ModerationDecision.verdict)
    rows = (await session.execute(stmt)).all()
    await session.commit()
    return [(r[0], r[1]) for r in rows]


async def test_patch_me_blocks_and_logs(client: httpx.AsyncClient, session: AsyncSession) -> None:
    pair = await sign_up(client)
    refused = await client.patch(
        "/v1/me", json={"display_name": "The Badword"}, headers=auth_header(pair)
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "moderation_blocked"
    flagged = await client.patch(
        "/v1/me", json={"display_name": "Spammy Sam"}, headers=auth_header(pair)
    )
    assert flagged.status_code == 200
    assert flagged.json()["display_name"] == "Spammy Sam"
    assert await decisions(session) == [("display_name", "block"), ("display_name", "flag")]


async def test_sign_up_refuses_blocked_name_and_keeps_token(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    sent = await send(client)
    token = (await verify(client, sent.json()["challenge_id"])).json()["pending_signup_token"]
    body = {"pending_signup_token": token, "date_of_birth": "2000-01-01"}
    refused = await client.post(
        "/v1/auth/sign-up/complete", json={**body, "display_name": "b a d w o r d"}
    )
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "moderation_blocked"
    done = await client.post("/v1/auth/sign-up/complete", json={**body, "display_name": "Rahim"})
    assert done.status_code == 201, done.text
    names = (await session.execute(select(User.display_name))).scalars().all()
    await session.commit()
    assert names == ["Rahim"]

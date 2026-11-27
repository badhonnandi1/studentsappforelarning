"""Step-up OTP, unlink, restricted mode and the dormant rule (05 §C.4–C.5, R-25)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security.hashing import keyed_hash
from app.modules.auth.internal.models import DeviceSession, ExternalIdentity, User
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.conftest import (
    PHONE,
    TEST_CODE,
    auth_header,
    send,
    sign_in,
    sign_up,
    verify,
)
from tests.support.social import provider_body

pytestmark = [pytest.mark.api, pytest.mark.db, pytest.mark.usefixtures("fakes")]


async def step_up(
    client: httpx.AsyncClient, headers: dict[str, str], action: str = "unlink"
) -> str:
    sent = await client.post("/v1/auth/step-up/send", json={"action": action}, headers=headers)
    assert sent.status_code == 202, sent.text
    body = {"action": action, "otp_challenge_id": sent.json()["challenge_id"], "code": TEST_CODE}
    done = await client.post("/v1/auth/step-up", json=body, headers=headers)
    assert done.status_code == 200, done.text
    return str(done.json()["step_up_token"])


async def linked_phone_user(client: httpx.AsyncClient) -> dict[str, str]:
    headers = auth_header(await sign_up(client))
    linked = await client.post(
        "/v1/me/identities/google", json=await provider_body(client, "google"), headers=headers
    )
    assert linked.status_code == 201, linked.text
    assert linked.json()["email_masked"] == "k***@example.com"
    return headers


def code(response: httpx.Response) -> Any:
    return response.json()["error"]["code"]


async def test_unlink_needs_step_up_then_succeeds_once(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    headers = await linked_phone_user(client)
    missing = await client.delete("/v1/me/identities/google", headers=headers)
    assert (missing.status_code, code(missing)) == (403, "step_up_required")
    wrong_action = await step_up(client, headers, "phone_change")
    crossed = await client.delete(
        "/v1/me/identities/google", headers={**headers, "X-Step-Up-Token": wrong_action}
    )
    assert code(crossed) == "step_up_required"
    token = await step_up(client, headers)
    with_token = {**headers, "X-Step-Up-Token": token}
    assert (await client.delete("/v1/me/identities/google", headers=with_token)).status_code == 204
    again = await client.delete("/v1/me/identities/google", headers=with_token)
    assert code(again) == "step_up_required"  # spent
    listed = (await client.get("/v1/me/identities", headers=headers)).json()
    assert listed == {"items": [], "phone_verified": True}
    async with sessions() as s, s.begin():
        row = (await s.execute(select(ExternalIdentity))).scalar_one()
        assert (row.unlink_reason, row.unlinked_at is not None) == ("user", True)
    relinked = await client.post(
        "/v1/me/identities/google", json=await provider_body(client, "google"), headers=headers
    )
    assert relinked.status_code == 201
    async with sessions() as s, s.begin():
        row = (await s.execute(select(ExternalIdentity))).scalar_one()  # the same row, reused
        assert (row.unlink_reason, row.unlinked_at) == (None, None)
        actions = set((await s.execute(select(AuditLog.action))).scalars())
        assert {"auth.identity.link", "auth.identity.unlink"} <= actions


async def test_step_up_refusals(client: httpx.AsyncClient) -> None:
    headers = auth_header(await sign_up(client))
    other = auth_header(await sign_up(client, "+8801700000002", device_id="device-0002"))
    sent = await client.post("/v1/auth/step-up/send", json={"action": "unlink"}, headers=other)
    body = {"action": "unlink", "otp_challenge_id": sent.json()["challenge_id"], "code": TEST_CODE}
    stolen = await client.post("/v1/auth/step-up", json=body, headers=headers)
    assert code(stolen) == "invalid_code"  # another account's challenge
    wrong = await client.post("/v1/auth/step-up", json={**body, "code": "000000"}, headers=other)
    assert (wrong.status_code, wrong.json()["error"]["details"]["attempts_left"]) == (401, 4)
    unknown = await client.delete("/v1/me/identities/facebook", headers=headers)
    assert code(unknown) == "step_up_required"
    token = await step_up(client, headers)
    gone = await client.delete(
        "/v1/me/identities/facebook", headers={**headers, "X-Step-Up-Token": token}
    )
    assert gone.status_code == 404


async def test_social_only_account_needs_a_phone(client: httpx.AsyncClient) -> None:
    body = await provider_body(
        client, "google", device={"device_id": "device-0009", "platform": "web"}
    )
    pair = (
        await client.post("/v1/auth/social/google", json={**body, "date_of_birth": "2001-01-01"})
    ).json()
    headers = auth_header(pair)
    unlink = await client.delete("/v1/me/identities/google", headers=headers)
    assert (unlink.status_code, code(unlink)) == (403, "phone_required")
    sent = await client.post("/v1/auth/step-up/send", json={"action": "unlink"}, headers=headers)
    assert code(sent) == "phone_required"
    listed = (await client.get("/v1/me/identities", headers=headers)).json()
    assert listed["phone_verified"] is False
    assert [i["provider"] for i in listed["items"]] == ["google"]


async def make_dormant(sessions: Callable[[], AsyncSession], clock: FrozenClock) -> None:
    async with sessions() as s, s.begin():
        user = (
            await s.execute(select(User).where(User.phone_hash == keyed_hash(PHONE, "phone")))
        ).scalar_one()
        user.last_seen_at = clock.now() - timedelta(days=181)


async def test_dormant_new_device_is_restricted(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession], clock: FrozenClock
) -> None:
    await sign_up(client)
    await make_dormant(sessions, clock)
    same_device = await sign_in(client)
    assert same_device["restricted_until"] is None  # a device the account has used
    await make_dormant(sessions, clock)
    pair = await sign_in(client, device_id="device-new-1")
    assert pair["restricted_until"] is not None
    headers = auth_header(pair)
    unlink = await client.delete("/v1/me/identities/google", headers=headers)
    assert (unlink.status_code, code(unlink)) == (403, "restricted_session")
    phone = await client.post("/v1/me/phone", json={"phone": "+8801700000003"}, headers=headers)
    assert code(phone) == "restricted_session"
    async with sessions() as s, s.begin():  # the 72 h pass
        stale = clock.now() - timedelta(seconds=1)
        await s.execute(update(DeviceSession).values(restricted_until=stale))
    unrestricted = await client.delete("/v1/me/identities/google", headers=headers)
    assert code(unrestricted) == "step_up_required"


async def test_dormant_with_linked_provider_needs_it(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession], clock: FrozenClock
) -> None:
    await linked_phone_user(client)
    await make_dormant(sessions, clock)
    sent = await send(client, device="device-new-2")
    second = await verify(client, sent.json()["challenge_id"], device_id="device-new-2")
    assert second.json() == {"status": "second_factor_required", "providers": ["google"]}
    body = await provider_body(
        client, "google", device={"device_id": "device-new-2", "platform": "android"}
    )
    via_google = await client.post("/v1/auth/social/google", json=body)
    assert via_google.status_code == 200
    assert via_google.json()["restricted_until"] is None

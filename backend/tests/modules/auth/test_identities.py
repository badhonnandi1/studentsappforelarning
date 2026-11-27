"""Linking from a session and the two-step phone change (05 §C.5, §D)."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.crypto import decrypt_field
from app.modules.auth.internal.models import User
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.conftest import TEST_CODE, auth_header, sign_up
from tests.modules.auth.test_step_up import code, step_up
from tests.support.social import provider_body

pytestmark = [pytest.mark.api, pytest.mark.db, pytest.mark.usefixtures("fakes")]
OTHER = "+8801700000002"
NEW = "+8801700000005"


async def link(client: httpx.AsyncClient, provider: str, headers: dict[str, str]) -> httpx.Response:
    body = await provider_body(client, provider)
    return await client.post(f"/v1/me/identities/{provider}", json=body, headers=headers)


async def test_link_conflicts_and_age_gate(client: httpx.AsyncClient) -> None:
    first = auth_header(await sign_up(client))
    second = auth_header(await sign_up(client, OTHER, dob="2016-05-05", device_id="device-0002"))
    assert (await link(client, "google", first)).status_code == 201
    in_use = await link(client, "google", second)
    assert (in_use.status_code, code(in_use)) == (409, "identity_in_use")
    again = await link(client, "google", first)
    assert (again.status_code, code(again)) == (409, "conflict")
    young = await link(client, "facebook", second)
    assert (young.status_code, code(young)) == (403, "age_restricted")
    bad = await client.post(
        "/v1/me/identities/google",
        json={"token": "nope-token-000000000", "nonce": "n" * 43},
        headers=first,
    )
    assert code(bad) == "invalid_nonce"


async def test_phone_change_two_steps(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    headers = auth_header(await sign_up(client))
    await sign_up(client, OTHER, device_id="device-0002")
    no_token = await client.post("/v1/me/phone", json={"phone": NEW}, headers=headers)
    assert (no_token.status_code, code(no_token)) == (403, "step_up_required")
    with_token = {**headers, "X-Step-Up-Token": await step_up(client, headers, "phone_change")}
    taken = await client.post("/v1/me/phone", json={"phone": OTHER}, headers=with_token)
    assert taken.status_code == 409
    same = await client.post("/v1/me/phone", json={"phone": "01700000001"}, headers=with_token)
    assert code(same) == "same_phone"
    started = await client.post("/v1/me/phone", json={"phone": NEW}, headers=with_token)
    assert started.status_code == 202, started.text
    challenge = started.json()["challenge_id"]
    reused = await client.post("/v1/me/phone", json={"phone": NEW}, headers=with_token)
    assert code(reused) == "step_up_required"  # the token is single use
    wrong = await client.post(
        "/v1/me/phone", json={"challenge_id": challenge, "code": "000000"}, headers=headers
    )
    assert code(wrong) == "invalid_code"
    done = await client.post(
        "/v1/me/phone", json={"challenge_id": challenge, "code": TEST_CODE}, headers=headers
    )
    assert done.status_code == 200, done.text
    assert done.json() == {"phone_masked": "01*******05"}
    async with sessions() as s, s.begin():
        users = (await s.execute(select(User))).scalars().all()
        phones = {decrypt_field(u.phone_enc, "identity.users.phone") for u in users if u.phone_enc}
        assert phones == {OTHER, NEW}
        assert "auth.phone.change" in set((await s.execute(select(AuditLog.action))).scalars())


async def test_phone_confirm_is_bound_to_the_caller(client: httpx.AsyncClient) -> None:
    body = await provider_body(
        client, "google", device={"device_id": "device-0003", "platform": "web"}
    )
    pair = await client.post("/v1/auth/social/google", json={**body, "date_of_birth": "2001-01-01"})
    social_only = auth_header(pair.json())
    started = await client.post("/v1/me/phone", json={"phone": NEW}, headers=social_only)
    assert started.status_code == 202, started.text  # adding a first number needs no step-up
    intruder = auth_header(await sign_up(client, OTHER, device_id="device-0004"))
    confirm = {"challenge_id": started.json()["challenge_id"], "code": TEST_CODE}
    stolen = await client.post("/v1/me/phone", json=confirm, headers=intruder)
    assert code(stolen) == "invalid_code"
    added = await client.post("/v1/me/phone", json=confirm, headers=social_only)
    assert added.status_code == 200
    me = await client.get("/v1/me/identities", headers=social_only)
    assert me.json()["phone_verified"] is True

"""Guardian consent and privacy settings (05 §D, NFR-07)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.modules.auth.internal.models import GuardianConsent, PrivacySetting
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.conftest import PHONE, TEST_CODE, auth_header, sign_up

pytestmark = [pytest.mark.api, pytest.mark.db]
GUARDIAN = "+8801700000002"
VERSION = "2026-11-v1"
MINOR_DOB = "2012-03-03"


def start_body(**changes: Any) -> dict[str, Any]:
    body = {"guardian_phone": GUARDIAN, "guardian_relation": "mother", "consent_version": VERSION}
    return {**body, **changes}


async def start(
    client: httpx.AsyncClient, headers: dict[str, str], **changes: Any
) -> httpx.Response:
    return await client.post(
        "/v1/me/consent/guardian/start", json=start_body(**changes), headers=headers
    )


async def confirm(
    client: httpx.AsyncClient, headers: dict[str, str], challenge_id: str, code: str = TEST_CODE
) -> httpx.Response:
    body = {"challenge_id": challenge_id, "code": code}
    return await client.post("/v1/me/consent/guardian/confirm", json=body, headers=headers)


async def test_guardian_consent_flow(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    pair = await sign_up(client, dob=MINOR_DOB)
    headers = auth_header(pair)
    assert pair["user"]["needs_consent"] is True
    started = await start(client, headers)
    assert started.status_code == 202, started.text
    challenge = started.json()["challenge_id"]
    wrong = await confirm(client, headers, challenge, "000000")
    assert wrong.status_code == 401
    done = await confirm(client, headers, challenge)
    assert done.status_code == 200, done.text
    assert done.json()["consent"]["status"] == "granted"
    assert done.json()["consent"]["version"] == VERSION
    me = (await client.get("/v1/me", headers=headers)).json()
    assert me["consent"] == {"required": True, "status": "granted"}
    assert (await client.get("/v1/me/profile", headers=headers)).json()["needs_consent"] is False
    assert (await start(client, headers)).status_code == 409  # already active
    assert (await confirm(client, headers, challenge)).status_code == 410  # used
    async with sessions() as s, s.begin():
        row = (await s.execute(select(GuardianConsent))).scalar_one()
        assert row.scope == {"relation": "mother"}
        assert b"8801700000002" not in row.guardian_phone_enc
        audit = await s.execute(
            select(AuditLog.action).where(AuditLog.action == "auth.guardian_consent.record")
        )
        assert audit.scalar_one_or_none() is not None
        await s.execute(update(GuardianConsent).values(withdrawn_at=row.granted_at))
    again = (await client.get("/v1/me", headers=headers)).json()
    assert again["consent"]["status"] == "missing"  # withdrawn: consent needed again


@pytest.mark.parametrize(
    ("changes", "status", "code"),
    [
        ({"guardian_phone": PHONE}, 422, "same_phone"),
        ({"consent_version": "2020-01-v0"}, 422, "consent_version_outdated"),
        ({"guardian_phone": "12345"}, 422, "invalid_phone"),
        ({"guardian_relation": "uncle"}, 422, None),
    ],
)
async def test_start_refusals(
    client: httpx.AsyncClient, changes: dict[str, Any], status: int, code: str | None
) -> None:
    headers = auth_header(await sign_up(client, dob=MINOR_DOB))
    response = await start(client, headers, **changes)
    assert response.status_code == status, response.text
    if code is not None:
        assert response.json()["error"]["code"] == code


async def test_adults_do_not_need_consent(client: httpx.AsyncClient) -> None:
    headers = auth_header(await sign_up(client, dob="2000-01-01"))
    response = await start(client, headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "consent_not_required"


async def test_challenge_belongs_to_the_minor(client: httpx.AsyncClient) -> None:
    minor = auth_header(await sign_up(client, dob=MINOR_DOB))
    other = auth_header(await sign_up(client, "+8801700000003", dob=MINOR_DOB))
    challenge = (await start(client, minor)).json()["challenge_id"]
    assert (await confirm(client, other, challenge)).status_code == 401
    await get_redis().delete(f"auth:guardian:{challenge}")
    assert (await confirm(client, minor, challenge)).status_code == 401  # binding gone


async def test_privacy_defaults_and_opt_out(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    pair = await sign_up(client, dob=MINOR_DOB)
    headers = auth_header(pair)
    url = "/v1/me/privacy"
    got = (await client.get(url, headers=headers)).json()
    assert got == {"leaderboard_visible": True, "profile_private": True, "opt_out_by": None}
    hidden = await client.put(url, json={"leaderboard_visible": False}, headers=headers)
    assert hidden.json()["opt_out_by"] == "self"
    shown = await client.put(
        url, json={"leaderboard_visible": True, "profile_private": False}, headers=headers
    )
    assert shown.json() == {
        "leaderboard_visible": True,
        "profile_private": False,
        "opt_out_by": None,
    }
    async with sessions() as s, s.begin():
        await s.execute(
            update(PrivacySetting).values(leaderboard_visible=False, opt_out_by="guardian")
        )
    refused = await client.put(url, json={"leaderboard_visible": True}, headers=headers)
    assert refused.status_code == 403
    same = await client.put(
        url, json={"leaderboard_visible": False, "profile_private": True}, headers=headers
    )
    assert same.json() == {
        "leaderboard_visible": False,
        "profile_private": True,
        "opt_out_by": "guardian",
    }


async def test_consent_document(client: httpx.AsyncClient) -> None:
    en = await client.get(f"/v1/consent-documents/{VERSION}", params={"lang": "en"})
    assert en.status_code == 200
    assert en.json()["body_markdown"].startswith("# Guardian consent")
    assert en.headers["Cache-Control"] == "public, max-age=86400"
    bn = await client.get(f"/v1/consent-documents/{VERSION}")
    assert bn.json()["lang"] == "bn"
    assert (await client.get("/v1/consent-documents/1999-v9")).status_code == 404
    assert (
        await client.get(f"/v1/consent-documents/{VERSION}", params={"lang": "fr"})
    ).status_code == 422

"""End to end over the API (05 §C.1 step 12): OTP sign-up → profile → guardian consent →
refresh → revoke, on the seeded reference data."""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from scripts import seed_reference
from tests.modules.auth.conftest import DEVICE, TEST_CODE, auth_header, send, verify

pytestmark = [pytest.mark.api, pytest.mark.db]
GUARDIAN = "+8801700000002"
CONSENT_VERSION = "2026-11-v1"


async def test_student_journey(client: httpx.AsyncClient, session: AsyncSession) -> None:
    await seed_reference.seed(session)

    sent = await send(client)
    assert sent.status_code == 202, sent.text
    pending = (await verify(client, sent.json()["challenge_id"])).json()
    assert pending["status"] == "needs_profile"
    body = {"pending_signup_token": pending["pending_signup_token"], "date_of_birth": "2011-06-01",
            "display_name": "Rahim"}  # fmt: skip
    signed_up = await client.post("/v1/auth/sign-up/complete", json=body)
    assert signed_up.status_code == 201, signed_up.text
    pair = signed_up.json()
    headers = auth_header(pair)
    assert pair["user"]["needs_consent"] is True

    profile = {"class_level": 9, "group_code": "science", "version_lang": "bn",
               "curriculum": "general", "district_id": 26, "exam_year": 2028}  # fmt: skip
    saved = await client.put("/v1/me/profile", json=profile, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["needs_consent"] is True

    consent = {"guardian_phone": GUARDIAN, "guardian_relation": "father",
               "consent_version": CONSENT_VERSION}  # fmt: skip
    started = await client.post("/v1/me/consent/guardian/start", json=consent, headers=headers)
    assert started.status_code == 202, started.text
    confirm = {"challenge_id": started.json()["challenge_id"], "code": TEST_CODE}
    granted = await client.post("/v1/me/consent/guardian/confirm", json=confirm, headers=headers)
    assert granted.status_code == 200, granted.text
    me = (await client.get("/v1/me", headers=headers)).json()
    assert me["consent"] == {"required": True, "status": "granted"}

    refreshed = await client.post("/v1/auth/refresh", json={"refresh_token": pair["refresh_token"]})
    assert refreshed.status_code == 200, refreshed.text
    new_headers = auth_header(refreshed.json())
    assert (await client.get("/v1/me", headers=new_headers)).status_code == 200

    sessions = (await client.get("/v1/me/sessions", headers=new_headers)).json()
    assert [(s["platform"], s["current"]) for s in sessions["items"]] == [
        (DEVICE["platform"], True)
    ]
    session_id = sessions["items"][0]["session_id"]
    revoked = await client.delete(f"/v1/me/sessions/{session_id}", headers=new_headers)
    assert revoked.status_code == 204
    assert (await client.get("/v1/me", headers=new_headers)).status_code == 401
    stale = await client.post(
        "/v1/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]}
    )
    assert stale.status_code == 401

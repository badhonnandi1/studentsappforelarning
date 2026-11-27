"""Facebook data deletion and deauthorise callbacks (05 §C.5)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.settings import get_settings
from app.modules.auth.internal.models import DataRequest, ExternalIdentity
from app.modules.auth.internal.services.meta_callbacks import parse_signed_request
from app.modules.ops.internal.models import AuditLog
from tests.support.users import make_user

pytestmark = [pytest.mark.api, pytest.mark.db]
SECRET = "meta-app-secret-for-tests-0000000"
DELETE = "/v1/webhooks/facebook/data-deletion"


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def signed(payload: dict[str, Any], secret: str = SECRET) -> str:
    body = b64(json.dumps(payload).encode())
    return f"{b64(hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())}.{body}"


@pytest.fixture(autouse=True)
def facebook_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "facebook_enabled", True)
    monkeypatch.setattr(get_settings(), "facebook_app_secret", SecretStr(SECRET))
    monkeypatch.setattr(get_settings(), "public_api_url", "https://api.example.com/")


async def linked(sessions: Callable[[], AsyncSession], subject: str = "fb-77") -> None:
    async with sessions() as s, s.begin():
        user = await make_user(s)
        s.add(ExternalIdentity(user_id=user.id, provider="facebook", provider_subject=subject))


def test_parse_rejects_tampering() -> None:
    good = {"algorithm": "HMAC-SHA256", "user_id": "1", "issued_at": 1}
    assert parse_signed_request(signed(good), SECRET)["user_id"] == "1"
    for bad in (
        signed(good, "other-secret"),
        signed({**good, "algorithm": "HMAC-SHA1"}),
        signed({"algorithm": "HMAC-SHA256"}),
        signed(good).split(".")[0] + "." + b64(b'{"user_id": "2", "algorithm": "HMAC-SHA256"}'),
        "no-dot-at-all",
        "!!!.###",
        signed(good).split(".")[0] + "." + b64(b"[1]"),
    ):
        with pytest.raises(AppError):
            parse_signed_request(bad, SECRET)


async def test_data_deletion_unlinks_and_records(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    await linked(sessions)
    form = {"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": "fb-77"})}
    first = await client.post(DELETE, data=form)
    assert first.status_code == 200, first.text
    code = first.json()["confirmation_code"]
    assert (
        first.json()["url"]
        == f"https://api.example.com/v1/auth/social/facebook/deletion-status/{code}"
    )
    again = await client.post(DELETE, data=form)
    assert again.json()["confirmation_code"] == code  # one open request per user
    status = await client.get(f"/v1/auth/social/facebook/deletion-status/{code}")
    assert status.json() == {"status": "received", "completed_at": None}
    async with sessions() as s, s.begin():
        row = (await s.execute(select(ExternalIdentity))).scalar_one()
        assert row.unlink_reason == "data_deletion"
        request = (await s.execute(select(DataRequest))).scalar_one()
        assert (request.kind, request.requested_via) == ("deletion", "facebook_callback")
        request.status, request.completed_at = "completed", request.created_at
    done = await client.get(f"/v1/auth/social/facebook/deletion-status/{code}")
    assert done.json()["status"] == "completed"
    assert done.json()["completed_at"] is not None


async def test_unknown_user_bad_signature_and_disabled(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    unknown = await client.post(
        DELETE, data={"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": "nobody"})}
    )
    assert unknown.status_code == 200
    code = unknown.json()["confirmation_code"]
    assert (await client.get(f"/v1/auth/social/facebook/deletion-status/{code}")).status_code == 404
    bad = await client.post(DELETE, data={"signed_request": signed({"user_id": "1"}, "wrong")})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "bad_request"
    assert "details" not in bad.json()["error"] or not bad.json()["error"]["details"]
    monkeypatch.setattr(get_settings(), "facebook_enabled", False)
    assert (await client.post(DELETE, data={"signed_request": "a.b"})).status_code == 404


async def test_deauthorize_unlinks_and_audits(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    await linked(sessions, "fb-88")
    form = {"signed_request": signed({"algorithm": "HMAC-SHA256", "user_id": "fb-88"})}
    response = await client.post("/v1/webhooks/facebook/deauthorize", data=form)
    assert (response.status_code, response.json()) == (200, {})
    async with sessions() as s, s.begin():
        row = (await s.execute(select(ExternalIdentity))).scalar_one()
        assert (row.unlink_reason, row.unlinked_at is not None) == ("deauthorized", True)
        actions = set((await s.execute(select(AuditLog.action))).scalars())
        assert "auth.identity.deauthorize" in actions

"""Staff SSO with enforced 2FA (R-07): fake IdP → admin tokens, and every refusal path."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.security.hashing import keyed_hash
from app.core.security.jwt import token_keys
from app.core.settings import get_settings
from app.modules.auth.internal.models import DeviceSession
from app.modules.auth.internal.services import staff_sso
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.test_providers_edge import redis_down
from tests.support.idp import DOMAIN, EMAIL, REDIRECT, FakeIdp
from tests.support.users import grant_role, make_user

pytestmark = [pytest.mark.api, pytest.mark.db]
START, CALLBACK = "/v1/admin/auth/sso/start", "/v1/admin/auth/sso/callback"


@pytest.fixture
def idp(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeIdp]:
    fake = FakeIdp()
    monkeypatch.setattr(get_settings(), "staff_oidc_redirect_uris", [REDIRECT])
    monkeypatch.setattr(get_settings(), "staff_oidc_allowed_domains", [DOMAIN.upper()])
    staff_sso.use_client(fake.client)
    yield fake
    staff_sso.use_client(None)


async def staff_user(
    sessions: Callable[[], AsyncSession], *, role: str | None = "ops_admin", verified: bool = True
) -> uuid.UUID:
    async with sessions() as s, s.begin():
        user = await make_user(
            s,
            date_of_birth=date(1990, 1, 1),
            email_hash=keyed_hash(EMAIL, "email"),
            email_verified_at=datetime.now(UTC) if verified else None,
        )
        if role is not None:
            await grant_role(s, user.id, role)
        return user.id


async def sso(client: httpx.AsyncClient, idp: FakeIdp) -> httpx.Response:
    start = await client.get(START, params={"redirect_uri": REDIRECT})
    assert start.status_code == 302, start.text
    code, state = idp.authorize(start.headers["location"])
    return await client.get(CALLBACK, params={"code": code, "state": state})


async def test_mfa_sign_in_issues_admin_tokens(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    sessions: Callable[[], AsyncSession],
    clock: FrozenClock,
) -> None:
    user_id = await staff_user(sessions)
    start = await client.get(START, params={"redirect_uri": REDIRECT})
    location = start.headers["location"]
    assert location.startswith("https://idp.example/authorize?")
    assert "code_challenge_method=S256" in location
    assert "client_id=staff-client" in location
    assert start.headers["cache-control"] == "no-store"
    code, state = idp.authorize(location)
    response = await client.get(
        CALLBACK, params={"code": code, "state": state}, headers={"X-Device-Id": "admin-laptop-1"}
    )
    assert response.status_code == 200, response.text
    pair = response.json()
    claims = token_keys().verify(pair["access_token"], audience="admin", now=clock.now())
    assert (claims["sub"], claims["sso"], claims["amr"]) == (str(user_id), True, ["mfa"])
    refresh_at = datetime.fromisoformat(pair["refresh_expires_at"])
    assert refresh_at == clock.now() + timedelta(hours=12)
    replay = await client.get(CALLBACK, params={"code": code, "state": state})
    assert replay.status_code == 400  # state is single use
    async with sessions() as s, s.begin():
        ds = (await s.execute(select(DeviceSession))).scalar_one()
        assert (ds.audience, ds.sign_in_method, ds.device_id) == ("admin", "sso", "admin-laptop-1")
        audit = (
            await s.execute(select(AuditLog).where(AuditLog.action == "auth.staff_sign_in"))
        ).scalar_one()
        assert audit.after == {"amr": ["pwd", "mfa"], "domain": DOMAIN, "roles": ["ops_admin"]}
        assert EMAIL not in str(audit.after)


@pytest.mark.parametrize(
    ("claims", "code"),
    [
        ({"amr": ["pwd"]}, "mfa_required"),
        ({"amr": "mfa"}, "mfa_required"),
        ({"email": "ops@other.example"}, "forbidden"),
        ({"email_verified": False}, "forbidden"),
        ({"hd": "other.example"}, "forbidden"),
    ],
)
async def test_claims_without_mfa_or_allowed_domain_are_refused(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    sessions: Callable[[], AsyncSession],
    claims: dict[str, Any],
    code: str,
) -> None:
    await staff_user(sessions)
    idp.claims.update(claims)
    response = await sso(client, idp)
    assert (response.status_code, response.json()["error"]["code"]) == (403, code)


@pytest.mark.parametrize(
    ("role", "verified"), [(None, True), ("student", True), ("ops_admin", False)]
)
async def test_requires_existing_staff_grant(
    client: httpx.AsyncClient,
    idp: FakeIdp,
    sessions: Callable[[], AsyncSession],
    role: str | None,
    verified: bool,
) -> None:
    await staff_user(sessions, role=role, verified=verified)
    response = await sso(client, idp)
    assert (response.status_code, response.json()["error"]["code"]) == (403, "forbidden")


async def test_unknown_user_bad_input_and_idp_failures(
    client: httpx.AsyncClient, idp: FakeIdp, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (await sso(client, idp)).status_code == 403  # nobody has this email
    other = await client.get(START, params={"redirect_uri": "https://evil.example/cb"})
    assert other.status_code == 400
    bad_state = await client.get(CALLBACK, params={"code": "c", "state": "s" * 32})
    assert bad_state.status_code == 400
    idp.token_status = 400
    failed = await sso(client, idp)
    assert (failed.status_code, failed.json()["error"]["code"]) == (401, "invalid_provider_token")
    idp.down, idp.token_status = True, 200
    start = await client.get(START, params={"redirect_uri": REDIRECT})
    assert start.status_code == 302  # discovery is cached
    code, state = idp.authorize(start.headers["location"])
    down = await client.get(CALLBACK, params={"code": code, "state": state})
    assert down.status_code == 503
    staff_sso.use_client(None)
    monkeypatch.setattr(get_settings(), "staff_oidc_client_id", "")
    assert (await client.get(START, params={"redirect_uri": REDIRECT})).status_code == 404


async def test_redis_down_is_503_and_client_comes_from_settings(
    client: httpx.AsyncClient, idp: FakeIdp, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis_down()
    assert (await client.get(START, params={"redirect_uri": REDIRECT})).status_code == 503
    state = await client.get(CALLBACK, params={"code": "c", "state": "s" * 32})
    assert state.status_code == 503
    staff_sso.use_client(None)
    monkeypatch.setattr(get_settings(), "staff_oidc_client_id", "configured")
    built = staff_sso.client()
    assert (built.issuer, built.client_id) == (get_settings().staff_oidc_issuer, "configured")

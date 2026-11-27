"""Social sign-in (05 §C.5): nonce, linking rules, DOB before creation, age gate."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.crypto import encrypt_field
from app.core.security.hashing import keyed_hash
from app.core.settings import get_settings
from app.modules.auth.internal.models import ExternalIdentity, User
from app.modules.auth.internal.providers import registry
from app.modules.auth.internal.providers.base import ProviderError, VerifiedIdentity
from app.modules.ops.internal.models import AuditLog
from tests.modules.auth.conftest import DEVICE
from tests.support.users import make_user

pytestmark = [pytest.mark.api, pytest.mark.db]
GOOGLE = VerifiedIdentity("google", "g-1", "kid@example.com", True, "Kid One")
FACEBOOK = VerifiedIdentity("facebook", "fb-1", "kid@example.com", False, "Kid One")


class FakeProvider:
    def __init__(self, name: str) -> None:
        self.name, self.tokens = name, {}  # type: ignore[var-annotated]

    async def verify(self, token: str, nonce: str) -> VerifiedIdentity:
        del nonce
        if token not in self.tokens:
            raise ProviderError()
        result: VerifiedIdentity = self.tokens[token]
        return result


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, FakeProvider]]:
    monkeypatch.setattr(get_settings(), "google_enabled", True)
    monkeypatch.setattr(get_settings(), "facebook_enabled", True)
    made = {name: FakeProvider(name) for name in ("google", "facebook")}
    for name, fake in made.items():
        fake.tokens[f"{name}-token-0000000000"] = GOOGLE if name == "google" else FACEBOOK
        registry.use_provider(name, fake)
    yield made
    for name in made:
        registry.use_provider(name, None)


async def social(
    client: httpx.AsyncClient, provider: str, *, token: str | None = None, **extra: Any
) -> httpx.Response:
    nonce = (await client.post("/v1/auth/social/nonce", json={"provider": provider})).json()[
        "nonce"
    ]
    body = {
        "token": token or f"{provider}-token-0000000000",
        "nonce": nonce,
        "device": DEVICE,
        **extra,
    }
    return await client.post(f"/v1/auth/social/{provider}", json=body)


async def count(sessions: Callable[[], AsyncSession], model: Any) -> int:
    async with sessions() as s, s.begin():
        return int((await s.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.mark.usefixtures("fakes")
async def test_new_account_needs_dob_then_signs_in(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    first = await social(client, "google")
    assert first.json()["status"] == "needs_profile"
    assert await count(sessions, User) == 0  # R-24: nothing created
    done = await client.post(
        "/v1/auth/sign-up/complete",
        json={
            "pending_signup_token": first.json()["pending_signup_token"],
            "date_of_birth": "2010-02-02",
        },
    )
    assert done.status_code == 201, done.text
    assert done.json()["user"]["needs_consent"] is True
    again = await social(client, "google")
    assert again.status_code == 200, again.text
    assert (again.json()["created"], again.json()["linked"]) == (False, False)
    async with sessions() as s, s.begin():
        user = (await s.execute(select(User))).scalar_one()
        assert user.email_verified_at is not None
        assert b"kid@example.com" not in (user.email_enc or b"")


@pytest.mark.usefixtures("fakes")
async def test_sign_in_with_dob_creates_directly(client: httpx.AsyncClient) -> None:
    response = await social(client, "facebook", date_of_birth="2008-01-01")
    assert response.status_code == 200, response.text
    assert response.json()["created"] is True


@pytest.mark.usefixtures("fakes")
async def test_facebook_under_13_is_refused_before_creation(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    young = await social(client, "facebook", date_of_birth="2016-01-01")
    assert young.status_code == 403
    assert young.json()["error"]["code"] == "age_restricted"
    pending = (await social(client, "facebook")).json()["pending_signup_token"]
    done = await client.post(
        "/v1/auth/sign-up/complete",
        json={"pending_signup_token": pending, "date_of_birth": "2016-01-01"},
    )
    assert done.status_code == 403
    assert await count(sessions, User) == 0
    google = await social(client, "google", date_of_birth="2016-01-01")
    assert google.status_code == 200  # the gate is Facebook-only


async def verified_email_user(sessions: Callable[[], AsyncSession], **fields: Any) -> None:
    async with sessions() as s, s.begin():
        await make_user(
            s, email_hash=keyed_hash("kid@example.com", "email"),
            email_enc=encrypt_field("kid@example.com", "identity.users.email"), **fields,
        )  # fmt: skip


@pytest.mark.usefixtures("fakes")
async def test_google_autolinks_verified_email_facebook_never(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    await verified_email_user(sessions, email_verified_at=func.now())
    linked = await social(client, "google")
    assert linked.status_code == 200, linked.text
    assert linked.json()["linked"] is True
    fb = await social(client, "facebook")
    assert fb.json()["status"] == "needs_profile"  # same email, but never auto-linked
    async with sessions() as s, s.begin():
        actions = (await s.execute(select(AuditLog.action))).scalars().all()
        assert "auth.identity_autolinked" in actions
        assert await s.scalar(select(func.count()).select_from(ExternalIdentity)) == 1


@pytest.mark.usefixtures("fakes")
async def test_unverified_email_is_not_linked(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    await verified_email_user(sessions)  # email present, never verified
    assert (await social(client, "google")).json()["status"] == "needs_profile"
    created = await social(client, "google", date_of_birth="2001-01-01")
    assert created.json()["created"] is True  # the email stays with the first account
    assert await count(sessions, User) == 2


@pytest.mark.usefixtures("fakes")
async def test_refusals(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    bad_token = await social(client, "google", token="wrong-token-00000000")
    assert bad_token.status_code == 401
    assert bad_token.json()["error"]["code"] == "invalid_provider_token"
    body = {"token": "google-token-0000000000", "nonce": "n" * 43, "device": DEVICE}
    unknown_nonce = await client.post("/v1/auth/social/google", json=body)
    assert unknown_nonce.json()["error"]["code"] == "invalid_nonce"
    nonce = (await client.post("/v1/auth/social/nonce", json={"provider": "facebook"})).json()[
        "nonce"
    ]
    crossed = await client.post("/v1/auth/social/google", json={**body, "nonce": nonce})
    assert crossed.json()["error"]["code"] == "invalid_nonce"  # issued for another provider
    assert (await client.post("/v1/auth/social/apple", json=body)).status_code == 404
    monkeypatch.setattr(get_settings(), "facebook_enabled", False)
    assert (
        await client.post("/v1/auth/social/nonce", json={"provider": "facebook"})
    ).status_code == 404
    assert (await social(client, "google", date_of_birth="2031-01-01")).status_code == 422


@pytest.mark.usefixtures("fakes")
async def test_suspended_account_and_kill_switch(
    client: httpx.AsyncClient, sessions: Callable[[], AsyncSession]
) -> None:
    from app.modules.nfr.internal.models import RuntimeConfig

    async with sessions() as s, s.begin():
        s.add(RuntimeConfig(key="kill.registrations", value=True, description="x"))
    closed = await social(client, "google", date_of_birth="2001-01-01")
    assert closed.status_code == 503
    assert closed.json()["error"]["code"] == "kill_switch"
    async with sessions() as s, s.begin():
        user = await make_user(s, status="suspended")
        s.add(ExternalIdentity(user_id=user.id, provider="facebook", provider_subject="fb-1"))
    assert (await social(client, "facebook")).status_code == 403

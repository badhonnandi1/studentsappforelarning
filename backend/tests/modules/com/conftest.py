"""COM fixtures: a moderator, an API client with COM's routers, a fresh term index, and AUTH's
session revoker (registered by ``auth.startup`` in the app)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, get_clock
from app.core.db import get_session
from app.core.http import create_app
from app.core.security import actor as actor_mod
from app.core.security.actor import Grant
from app.core.settings import Settings
from app.modules import com
from app.modules.auth.internal.models import User
from app.modules.auth.internal.schemas.auth import DeviceInfo
from app.modules.auth.internal.services import sign_in
from app.modules.auth.internal.services.sessions import BanRevoker
from app.modules.com.internal.models import ModerationTerm
from app.modules.com.internal.repositories import terms as terms_repo
from app.modules.com.internal.services.moderate import fold_term
from tests.support.tokens import bearer, ensure_keys, staff_token
from tests.support.users import make_user

MODERATOR = uuid.UUID("00000000-0000-7000-8000-0000000000c1")
OUTSIDER = uuid.UUID("00000000-0000-7000-8000-0000000000c2")


async def loader(user_id: uuid.UUID) -> list[Grant]:
    return [Grant("moderation")] if user_id == MODERATOR else []


@pytest.fixture(autouse=True)
def grants_terms_revoker() -> Iterator[None]:
    """The fake grants loader, a fresh term index and AUTH's real session revoker."""
    actor_mod.set_grants_loader(loader)
    com.set_session_revoker(BanRevoker())
    terms_repo.invalidate()
    ensure_keys()
    yield
    actor_mod.set_grants_loader(None)
    com.set_session_revoker(None)
    terms_repo.invalidate()


async def signed_in(
    session: AsyncSession, user_id: uuid.UUID, now: datetime, device: str = "device-c001"
) -> str:
    """Start a real AUTH device session for ``user_id``; return its access token."""
    info = DeviceInfo(device_id=device, platform="android", app_version="1.0.0")
    async with session.begin():
        user = await session.get(User, user_id)
        assert user is not None
        started = await sign_in.start_session(session, user, "otp", info, ip=None, now=now)
    return started.pair.access_token


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime.now(UTC))


@pytest.fixture
async def staff(session: AsyncSession) -> uuid.UUID:
    async with session.begin():
        await make_user(session, MODERATOR)
        await make_user(session, OUTSIDER)
    return MODERATOR


def as_staff(user_id: uuid.UUID = MODERATOR) -> dict[str, str]:
    return bearer(staff_token(user_id))


async def add_terms(session: AsyncSession, *terms: tuple[str, str, int]) -> None:
    """``(lang, raw term, severity)`` rows, stored folded like the admin route does."""
    async with session.begin():
        for lang, raw, severity in terms:
            session.add(ModerationTerm(
                lang=lang, term_folded=fold_term(lang, raw), severity=severity, category="profanity"
            ))  # fmt: skip
    terms_repo.invalidate()


@pytest.fixture
async def client(
    session: AsyncSession, app_redis: Redis, clock: FrozenClock
) -> AsyncIterator[httpx.AsyncClient]:
    del app_redis
    app = create_app("api", routers=com.routers(), settings=Settings(_env_file=None))

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_clock] = lambda: clock
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

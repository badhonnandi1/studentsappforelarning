"""The whole public API (every module's routers) on the test session, with real AUTH sessions
for students and SSO staff tokens whose grants come from a fixed table."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock, get_clock
from app.core.db import get_session
from app.core.http import create_app
from app.core.security import actor as actor_mod
from app.core.security import crypto
from app.core.security.actor import Grant
from app.core.security.jwt import token_keys
from app.core.settings import Settings
from app.core.storage import get_storage
from app.modules import com
from app.modules.auth.internal.models import User
from app.modules.auth.internal.schemas.auth import DeviceInfo
from app.modules.auth.internal.services import sign_in
from app.modules.auth.internal.services.sessions import BanRevoker
from app.modules.registry import all_routers
from tests.modules.auth.conftest import uploads_storage
from tests.support.tokens import bearer, ensure_keys, staff_token
from tests.support.users import make_user

STUDENT = uuid.UUID("00000000-0000-7000-8000-00000000a001")
OTHER_STUDENT = uuid.UUID("00000000-0000-7000-8000-00000000a002")
STAFF = uuid.UUID("00000000-0000-7000-8000-00000000a003")  # holds every B1 staff permission
STAFF_NO_GRANT = uuid.UUID("00000000-0000-7000-8000-00000000a004")
STAFF_PERMISSIONS = ("audit.read", "ops.config", "role.grant", "moderation")


async def grants(user_id: uuid.UUID) -> list[Grant]:
    return [Grant(p) for p in STAFF_PERMISSIONS] if user_id == STAFF else []


@pytest.fixture
def clock() -> FrozenClock:
    """Fallback for directories without their own ``clock`` (closer conftests override it)."""
    return FrozenClock(datetime.now(UTC))


@pytest.fixture
async def wired() -> AsyncIterator[None]:
    await crypto.init_crypto(Settings(_env_file=None))
    actor_mod.set_grants_loader(grants)
    com.set_session_revoker(BanRevoker())
    ensure_keys()
    yield
    actor_mod.set_grants_loader(None)
    com.set_session_revoker(None)


@pytest.fixture
async def people(session: AsyncSession, wired: None) -> None:
    del wired
    async with session.begin():
        for user_id in (STUDENT, OTHER_STUDENT, STAFF, STAFF_NO_GRANT):
            await make_user(session, user_id, date_of_birth=date(2000, 1, 1), display_name="Mim")


@pytest.fixture
async def api(
    session: AsyncSession, app_redis: Redis, clock: FrozenClock, people: None
) -> AsyncIterator[httpx.AsyncClient]:
    del app_redis, people
    app = create_app("api", routers=all_routers(), settings=Settings(_env_file=None))

    async def test_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_storage] = lambda: uploads_storage()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def student_session(
    session: AsyncSession, user_id: uuid.UUID, now: datetime
) -> tuple[dict[str, str], uuid.UUID]:
    """A fresh real device session: its Authorization header and session id."""
    info = DeviceInfo(device_id=f"dev-{uuid.uuid4().hex[:12]}", platform="android")
    async with session.begin():
        user = await session.get(User, user_id)
        assert user is not None
        started = await sign_in.start_session(session, user, "otp", info, ip=None, now=now)
    token = started.pair.access_token
    claims = token_keys().verify(token, audience="api", now=now)
    return bearer(token), uuid.UUID(claims["sid"])


def staff_header(user_id: uuid.UUID = STAFF) -> dict[str, str]:
    return bearer(staff_token(user_id, roles=("ops_admin",)))

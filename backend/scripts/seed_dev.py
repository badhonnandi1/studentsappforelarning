"""Local development data: one super admin, test students, and Google and Facebook test
identities created through the real account code (no provider is called).

    uv run python -m scripts.seed_dev

Runs only when ``APP_ENV`` is ``local`` or ``test``: there is no break-glass admin in staging
or prod (05 §C.8). It prints an admin access token from a real ``sso`` staff session, so local
admin routes can be tried without an IdP. Safe to rerun: existing rows are reused.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import dispose_engine, init_engine, sessionmaker
from app.core.ids import uuid7
from app.core.redis import close_redis, init_redis
from app.core.security.actor import SUPER_ADMIN
from app.core.security.crypto import init_crypto
from app.core.security.hashing import keyed_hash
from app.core.security.jwt import init_token_keys
from app.core.settings import Settings, get_settings
from app.modules.auth.internal.models import RoleGrant, User
from app.modules.auth.internal.providers.base import VerifiedIdentity
from app.modules.auth.internal.repositories import identities as identities_repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import DeviceInfo
from app.modules.auth.internal.services import accounts, sign_in

DEV_ENVS = frozenset({"local", "test"})
ADMIN_EMAIL = "admin@example.com"
ADULT_DOB = date(2004, 1, 1)
STUDENTS = (  # the reserved test block (R-31): never sent to an SMS gateway
    ("+8801700000101", "Rahim", date(2009, 3, 1)),
    ("+8801700000102", "Nusrat", date(2008, 7, 15)),
    ("+8801700000103", "Tanvir", ADULT_DOB),
)
SOCIAL = (
    VerifiedIdentity("google", "dev-google-0001", "google.student@example.com", True, "Mim"),
    VerifiedIdentity("facebook", "dev-facebook-0001", None, False, "Arif"),
)
ADMIN_DEVICE = DeviceInfo(device_id="seed-dev-admin", platform="web", app_version="1.0.0")


class DevOnlyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Seeded:
    admin_id: uuid.UUID
    student_ids: tuple[uuid.UUID, ...]
    social_ids: tuple[uuid.UUID, ...]
    admin_token: str


def require_dev(settings: Settings) -> None:
    if settings.app_env not in DEV_ENVS:
        raise DevOnlyError(f"seed_dev runs only in local or test, not {settings.app_env}")


async def _admin(session: AsyncSession, now: datetime) -> User:
    admin = await identities_repo.user_by_email(session, keyed_hash(ADMIN_EMAIL, "email"))
    if admin is None:
        admin = await accounts.create_user(
            session, dob=ADULT_DOB, display_name="Dev Admin", now=now, verified_email=ADMIN_EMAIL
        )
    if SUPER_ADMIN not in await users_repo.active_roles(session, admin.id):
        session.add(RoleGrant(id=uuid7(), user_id=admin.id, role_code=SUPER_ADMIN, granted_at=now))
        await session.flush()
    return admin


async def _students(session: AsyncSession, now: datetime) -> tuple[uuid.UUID, ...]:
    ids = []
    for phone, name, dob in STUDENTS:
        user = await users_repo.by_phone_hash(session, keyed_hash(phone, "phone"))
        if user is None:
            user = await accounts.create_user(
                session, dob=dob, display_name=name, now=now, phone=phone
            )
        ids.append(user.id)
    return tuple(ids)


async def _social(session: AsyncSession, now: datetime) -> tuple[uuid.UUID, ...]:
    ids = []
    for ident in SOCIAL:
        row = await identities_repo.by_subject(session, ident.provider, ident.subject)
        if row is not None and row.unlinked_at is None:
            ids.append(row.user_id)
            continue
        user = await accounts.create_social_account(
            session, ident, dob=ADULT_DOB, display_name=ident.name, now=now
        )
        ids.append(user.id)
    return tuple(ids)


async def seed(session: AsyncSession, settings: Settings, now: datetime) -> Seeded:
    require_dev(settings)
    async with session.begin():
        admin = await _admin(session, now)
        students = await _students(session, now)
        social = await _social(session, now)
        started = await sign_in.start_session(
            session, admin, "sso", ADMIN_DEVICE, ip=None, now=now, audience="admin"
        )
    await sign_in.after_commit(started)
    return Seeded(admin.id, students, social, started.pair.access_token)


async def main() -> None:
    settings = get_settings()
    require_dev(settings)
    init_engine(settings, "worker")
    init_redis(settings.redis_url)
    init_token_keys(settings)
    await init_crypto(settings)
    try:
        async with sessionmaker()() as session:
            result = await seed(session, settings, datetime.now(UTC))
    finally:
        await dispose_engine()
        await close_redis()
    print(f"super admin {result.admin_id} ({ADMIN_EMAIL})")
    print(f"students {', '.join(map(str, result.student_ids))}")
    print(f"social   {', '.join(map(str, result.social_ids))}")
    print(f"admin access token (15 min, local only):\n{result.admin_token}")


if __name__ == "__main__":
    asyncio.run(main())

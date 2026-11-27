"""Sign access tokens with the test keys (kid ``test-1``)."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from app.core.security.jwt import Audience, init_token_keys, token_keys
from app.core.settings import Settings

TTL = timedelta(minutes=15)


def ensure_keys() -> None:
    try:
        token_keys()
    except RuntimeError:
        init_token_keys(Settings(_env_file=None))


def access_token(
    user_id: uuid.UUID,
    *,
    session_id: uuid.UUID | None = None,
    roles: Iterable[str] = (),
    audience: Audience = "api",
    sso: bool = False,
    amr: Iterable[str] = (),
    now: datetime | None = None,
) -> str:
    ensure_keys()
    claims: dict[str, object] = {
        "sub": str(user_id),
        "sid": str(session_id or uuid.uuid4()),
        "roles": list(roles),
        "jti": uuid.uuid4().hex,
    }
    if audience == "admin":
        claims.update(sso=sso, amr=list(amr))
    when = now or datetime.now(UTC)
    return token_keys().sign(claims, audience=audience, now=when, ttl=TTL)


def staff_token(user_id: uuid.UUID, roles: Iterable[str] = ("ops_admin",), **kw: object) -> str:
    kw.setdefault("sso", True)
    kw.setdefault("amr", ["pwd", "mfa"])
    return access_token(user_id, roles=roles, audience="admin", **kw)  # type: ignore[arg-type]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}

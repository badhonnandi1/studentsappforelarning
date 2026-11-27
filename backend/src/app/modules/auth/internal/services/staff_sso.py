"""Staff sign-in through the organisation's IdP with enforced 2FA (R-07, 05 §C.12).

``start`` keeps ``{nonce, code_verifier, redirect_uri}`` in Redis for 10 min under a hash of a
random ``state`` and returns the IdP URL. ``callback`` takes the state once (GETDEL), trades the
code with PKCE, verifies the ID token, then requires, in order: an MFA method in ``amr``
(``403 mfa_required``), a verified email in an allowed domain, and an existing user with that
email hash holding a staff role (``403 forbidden``). Only then is an ``aud=admin`` session
started (``sso=true``, 12 h refresh that does not slide).
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from typing import Any, Final

from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import (
    AppError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    UnavailableError,
)
from app.core.redis import get_redis
from app.core.security.deps import MFA_METHODS
from app.core.security.hashing import keyed_hash, sha256
from app.core.security.jwks import IdpUnavailableError, InvalidTokenError
from app.core.security.oidc import OidcClient, pkce_pair
from app.core.settings import get_settings
from app.modules import ops
from app.modules.auth.internal.permissions import STAFF_ROLES
from app.modules.auth.internal.repositories import identities as identities_repo
from app.modules.auth.internal.repositories import users as users_repo
from app.modules.auth.internal.schemas.auth import DeviceInfo, TokenPair
from app.modules.auth.internal.services import sign_in

STATE_TTL_S: Final = 600
_override: OidcClient | None = None


def use_client(client: OidcClient | None) -> None:
    """Tests install a client pointed at a fake IdP."""
    global _override
    _override = client


def client() -> OidcClient:
    if _override is not None:
        return _override
    s = get_settings()
    if not (s.staff_oidc_issuer and s.staff_oidc_client_id):
        raise NotFoundError("Staff sign-in is not configured")
    secret = s.staff_oidc_client_secret.get_secret_value()
    return OidcClient(s.staff_oidc_issuer, s.staff_oidc_client_id, secret)


def _state_key(state: str) -> str:
    return f"auth:sso:state:{sha256(state).hex()}"


def _unavailable() -> UnavailableError:
    return UnavailableError("Staff sign-in is unavailable; try again shortly")


async def start(redirect_uri: str) -> str:
    if redirect_uri not in get_settings().staff_oidc_redirect_uris:
        raise AppError("redirect_uri is not allowed")
    oidc = client()
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier, challenge = pkce_pair()
    try:
        found = await oidc.discover()
        bound = {"nonce": nonce, "verifier": verifier, "redirect_uri": redirect_uri}
        await get_redis().set(_state_key(state), json.dumps(bound), ex=STATE_TTL_S)
    except (IdpUnavailableError, RedisError, OSError) as exc:
        raise _unavailable() from exc
    return oidc.authorize_url(
        found, redirect_uri=redirect_uri, state=state, nonce=nonce, challenge=challenge
    )


async def _take_state(state: str) -> dict[str, str]:
    try:
        raw = await get_redis().getdel(_state_key(state))
    except (RedisError, OSError) as exc:
        raise _unavailable() from exc
    if not raw:
        raise AppError("The sign-in link is invalid or has expired")
    bound: dict[str, str] = json.loads(raw)
    return bound


async def _claims(code: str, bound: dict[str, str], now: datetime) -> dict[str, Any]:
    oidc = client()
    try:
        token = await oidc.exchange(
            code, redirect_uri=bound["redirect_uri"], code_verifier=bound["verifier"]
        )
        return await oidc.verify(token, nonce=bound["nonce"], now=now.timestamp())
    except InvalidTokenError as exc:
        raise UnauthorizedError("Staff sign-in failed", code="invalid_provider_token") from exc
    except IdpUnavailableError as exc:
        raise _unavailable() from exc


def mfa_methods(claims: dict[str, Any]) -> list[str]:
    amr = claims.get("amr")
    methods = [str(m) for m in amr] if isinstance(amr, list) else []
    if not MFA_METHODS.intersection(methods):
        raise ForbiddenError("Two-step verification is required", code="mfa_required")
    return methods


def allowed_email(claims: dict[str, Any]) -> tuple[str, str]:
    """``(email, domain)``: verified, in an allowed domain, and consistent with ``hd``."""
    email = str(claims.get("email") or "").strip().lower()
    domain = email.rpartition("@")[2]
    allowed = {d.lower() for d in get_settings().staff_oidc_allowed_domains}
    hosted = claims.get("hd")
    if claims.get("email_verified") is not True or "@" not in email or domain not in allowed:
        raise ForbiddenError("This account cannot use staff sign-in")
    if hosted is not None and str(hosted).lower() != domain:
        raise ForbiddenError("This account cannot use staff sign-in")
    return email, domain


async def callback(
    session: AsyncSession,
    code: str,
    state: str,
    device: DeviceInfo,
    *,
    ip: str | None,
    now: datetime,
) -> TokenPair:
    claims = await _claims(code, await _take_state(state), now)
    amr = mfa_methods(claims)
    email, domain = allowed_email(claims)
    async with session.begin():
        user = await identities_repo.user_by_email(session, keyed_hash(email, "email"))
        roles = await users_repo.active_roles(session, user.id) if user is not None else []
        staff = sorted(STAFF_ROLES.intersection(roles))
        if user is None or user.email_verified_at is None or not staff:
            raise ForbiddenError("This account cannot use staff sign-in")
        started = await sign_in.start_session(
            session, user, "sso", device, ip=ip, now=now, audience="admin"
        )
        who = ops.AuditActor(kind="staff", user_id=user.id, roles=tuple(roles))
        target = ops.AuditTarget(type="device_session", id=str(started.session.id))
        async with ops.audited(session, who, "auth.staff_sign_in", target, now=now) as audit:
            audit.after = {"amr": amr, "domain": domain, "roles": staff}
    await sign_in.after_commit(started)
    return started.pair

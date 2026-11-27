"""FastAPI dependencies: ``current_actor`` (aud=api), ``admin_actor`` (aud=admin, SSO only)."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.clock import Clock, get_clock
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.ratelimit import enforce
from app.core.security.actor import Actor, is_session_revoked, load_grants, require
from app.core.security.jwt import Audience, token_keys

MFA_METHODS = frozenset({"mfa", "otp", "hwk", "swk"})


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError("Sign in required")
    return token.strip()


def _claims_actor(claims: dict[str, Any], audience: str) -> Actor:
    try:
        user_id, session_id = uuid.UUID(str(claims["sub"])), uuid.UUID(str(claims["sid"]))
        roles = frozenset(str(r) for r in claims.get("roles", []))
    except (KeyError, ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid token") from exc
    amr = tuple(str(m) for m in claims.get("amr", []))
    return Actor(user_id, session_id, roles, audience, claims.get("sso") is True, amr)


async def resolve_actor(request: Request, audience: Audience, clock: Clock) -> Actor:
    claims = token_keys().verify(bearer_token(request), audience=audience, now=clock.now())
    actor = _claims_actor(claims, audience)
    if await is_session_revoked(actor.session_id, fail_closed=audience == "admin"):
        raise UnauthorizedError("Session ended", code="session_revoked")
    grants = await load_grants(actor.user_id)
    return Actor(**{**actor.__dict__, "grants": grants})


async def current_actor(request: Request, clock: Annotated[Clock, Depends(get_clock)]) -> Actor:
    return await resolve_actor(request, "api", clock)


async def admin_actor(request: Request, clock: Annotated[Clock, Depends(get_clock)]) -> Actor:
    """Admin routes accept only SSO-issued tokens with an MFA ``amr`` (R-07)."""
    actor = await resolve_actor(request, "admin", clock)
    if not actor.sso or not MFA_METHODS.intersection(actor.amr):
        raise ForbiddenError("Staff sign-in through SSO with MFA is required", code="mfa_required")
    return actor


def staff_permission(permission: str) -> Callable[..., Awaitable[Actor]]:
    """``Depends(staff_permission("audit.read"))``: an SSO admin actor holding the permission,
    rate-limited on the admin tier per user."""

    async def dependency(actor: Annotated[Actor, Depends(admin_actor)]) -> Actor:
        await enforce("admin", {"user": str(actor.user_id)})
        require(actor, permission)
        return actor

    return dependency

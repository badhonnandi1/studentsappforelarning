"""AUTH (identity): identity, sessions, roles, profiles and consent. Public API of the module."""

from __future__ import annotations

from typing import Any

CODE = "AUTH"
SCHEMA = "identity"

__all__ = ["CODE", "SCHEMA", "routers"]


def routers() -> list[Any]:
    from app.modules.auth.internal.routes.auth import router as auth_router
    from app.modules.auth.internal.routes.me import router as me_router

    return [auth_router, me_router]

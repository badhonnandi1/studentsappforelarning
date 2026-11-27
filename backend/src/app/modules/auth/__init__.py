"""AUTH (identity): identity, sessions, roles, profiles and consent. Public API of the module."""

from __future__ import annotations

from typing import Any

CODE = "AUTH"
SCHEMA = "identity"

__all__ = ["CODE", "SCHEMA", "routers", "startup"]


def routers() -> list[Any]:
    from app.modules.auth.internal.routes.admin_roles import router as admin_roles_router
    from app.modules.auth.internal.routes.auth import router as auth_router
    from app.modules.auth.internal.routes.me import router as me_router
    from app.modules.auth.internal.routes.profile import router as profile_router
    from app.modules.auth.internal.routes.reference import router as reference_router

    return [auth_router, me_router, profile_router, reference_router, admin_roles_router]


def startup() -> None:
    """Register the DB-backed grants loader used by ``can``/``require`` (R-03)."""
    from app.core.db import sessionmaker
    from app.core.security.actor import set_grants_loader
    from app.modules.auth.internal.services.rbac import make_grants_loader

    set_grants_loader(make_grants_loader(lambda: sessionmaker()()))

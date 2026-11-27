"""COM (community): moderation, reports and restrictions. Public API of the module.

``moderate`` and ``ensure_allowed`` are the synchronous text check every module uses.
``is_restricted`` and ``is_banned`` are read on write paths and at sign-in. AUTH registers a
``SessionRevoker`` so a ban ends sessions without COM importing AUTH.
"""

from __future__ import annotations

from typing import Any

from app.modules.com.contracts.moderation import ModerationVerdict, SessionRevoker
from app.modules.com.internal.services.moderate import ensure_allowed, moderate

CODE = "COM"
SCHEMA = "community"

__all__ = [
    "CODE",
    "SCHEMA",
    "ModerationVerdict",
    "SessionRevoker",
    "ensure_allowed",
    "moderate",
    "routers",
]


def routers() -> list[Any]:
    from app.modules.com.internal.routes.admin_terms import router as terms_router

    return [terms_router]

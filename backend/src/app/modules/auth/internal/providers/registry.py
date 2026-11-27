"""Provider name → instance from settings. A disabled provider is ``404`` (05 §C.5 step 1)."""

from __future__ import annotations

from app.core.errors import NotFoundError
from app.core.settings import get_settings
from app.modules.auth.internal.providers.base import SocialProvider
from app.modules.auth.internal.providers.facebook import FacebookProvider
from app.modules.auth.internal.providers.google import GoogleProvider

_overrides: dict[str, SocialProvider] = {}


def use_provider(name: str, provider: SocialProvider | None) -> None:
    """Tests swap in a fake; ``None`` removes the override."""
    if provider is None:
        _overrides.pop(name, None)
    else:
        _overrides[name] = provider


def enabled(name: str) -> bool:
    settings = get_settings()
    return {"google": settings.google_enabled, "facebook": settings.facebook_enabled}.get(
        name, False
    )


def get(name: str) -> SocialProvider:
    if not enabled(name):
        raise NotFoundError("This sign-in method is not available")
    if name in _overrides:
        return _overrides[name]
    settings = get_settings()
    if name == "google":
        return GoogleProvider(settings.google_client_ids)
    return FacebookProvider(
        settings.facebook_app_id,
        settings.facebook_app_secret.get_secret_value(),
        settings.facebook_graph_version,
    )

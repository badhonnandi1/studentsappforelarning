"""Keyed lookup hashes (HMAC-SHA256, one key per purpose) and OTP hashing.

PII is looked up by ``*_hash`` columns; the keys never leave the secret store. Outside staging
and prod a missing key falls back to a fixed local key so a fresh checkout runs; the settings
validator refuses that in deployed environments.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Literal

from app.core.settings import Settings, get_settings

Purpose = Literal["phone", "email", "ip", "device"]


def _key(secret: str, label: str, settings: Settings) -> bytes:
    if secret:
        return secret.encode()
    if settings.is_deployed:  # pragma: no cover - the settings validator refuses this first
        raise RuntimeError(f"missing hash key for {label}")
    return hashlib.sha256(f"local-only-{label}".encode()).digest()


def keyed_hash(value: str, purpose: Purpose, settings: Settings | None = None) -> bytes:
    settings = settings or get_settings()
    secret = settings.pii_hash_keys.get(purpose)
    key = _key(secret.get_secret_value() if secret else "", purpose, settings)
    return hmac.new(key, value.encode(), hashlib.sha256).digest()


def otp_hash(code: str, challenge_id: str, settings: Settings | None = None) -> bytes:
    """Bound to the challenge id, so a hash leaked from one challenge matches no other."""
    settings = settings or get_settings()
    key = _key(settings.otp_hash_key.get_secret_value(), "otp", settings)
    return hmac.new(key, f"{challenge_id}:{code}".encode(), hashlib.sha256).digest()


def constant_time_equal(a: bytes, b: bytes) -> bool:
    return hmac.compare_digest(a, b)


def sha256(value: bytes | str) -> bytes:
    data = value.encode() if isinstance(value, str) else value
    return hashlib.sha256(data).digest()

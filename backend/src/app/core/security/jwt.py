"""EdDSA (Ed25519) JWTs with ``kid`` rotation (14 §1.2).

Every private key in ``JWT_PRIVATE_KEYS`` can verify, so two kids are valid during a rotation;
only ``JWT_ACTIVE_KID`` signs. Verify-only deployables use ``JWT_PUBLIC_KEYS``. Expiry is
checked against the injected clock, not the wall clock, so tests control time.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Literal

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from app.core.errors import UnauthorizedError
from app.core.settings import Settings

Audience = Literal["api", "admin", "exam-ingest"]
ALGORITHM = "EdDSA"
LEEWAY_S = 30


class TokenKeys:
    def __init__(
        self,
        private: Mapping[str, Ed25519PrivateKey],
        public: Mapping[str, Ed25519PublicKey],
        active: str | None,
    ) -> None:
        self.private, self.active = dict(private), active
        self.public = {**{k: v.public_key() for k, v in private.items()}, **public}

    @classmethod
    def from_settings(cls, settings: Settings) -> TokenKeys:
        private: dict[str, Ed25519PrivateKey] = {}
        for kid, secret in settings.jwt_private_keys.items():
            key = load_pem_private_key(secret.get_secret_value().encode(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError(f"JWT key {kid} is not Ed25519")
            private[kid] = key
        public: dict[str, Ed25519PublicKey] = {}
        for kid, pem in settings.jwt_public_keys.items():
            pub = load_pem_public_key(pem.encode())
            if not isinstance(pub, Ed25519PublicKey):
                raise ValueError(f"JWT public key {kid} is not Ed25519")
            public[kid] = pub
        return cls(private, public, settings.jwt_active_kid or None)

    def sign(
        self, claims: Mapping[str, Any], *, audience: Audience, now: datetime, ttl: timedelta
    ) -> str:
        if not self.active or self.active not in self.private:
            raise RuntimeError("no active JWT signing key")
        payload = {
            **claims,
            "aud": audience,
            "iat": int(now.timestamp()),
            "exp": int((now + ttl).timestamp()),
        }
        return jwt.encode(
            payload, self.private[self.active], algorithm=ALGORITHM, headers={"kid": self.active}
        )

    def verify(self, token: str, *, audience: Audience, now: datetime) -> dict[str, Any]:
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid token") from exc
        key = self.public.get(kid) if isinstance(kid, str) else None
        if key is None:
            raise UnauthorizedError("Invalid token")
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=[ALGORITHM],
                audience=audience,
                options={
                    "verify_exp": False,
                    "verify_iat": False,
                    "require": ["exp", "iat", "aud"],
                },
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError("Invalid token") from exc
        ts = now.timestamp()
        if claims["exp"] + LEEWAY_S < ts:
            raise UnauthorizedError("Token expired", code="token_expired")
        if claims["iat"] - LEEWAY_S > ts:
            raise UnauthorizedError("Invalid token")
        return claims


_keys: TokenKeys | None = None


def init_token_keys(settings: Settings) -> TokenKeys:
    global _keys
    _keys = TokenKeys.from_settings(settings)
    return _keys


def token_keys() -> TokenKeys:
    if _keys is None:
        raise RuntimeError("JWT keys not initialised; call init_token_keys() at startup")
    return _keys

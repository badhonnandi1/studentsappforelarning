"""Facebook token verification (05 §C.5).

Access tokens (Android, web): ``/debug_token`` with the app token proves the token was issued to
this app and is valid; ``/me`` (with ``appsecret_proof``) returns the profile. iOS Limited Login
sends an OIDC token instead, verified against Facebook's JWKS with ``aud = app_id`` and the
nonce. Facebook emails are never treated as verified. Neither token nor secret is ever logged.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any

import httpx

from app.modules.auth.internal.providers.base import ProviderError, VerifiedIdentity, fetch_json
from app.modules.auth.internal.providers.jwks import JwksCache, verify_id_token

GRAPH = "https://graph.facebook.com"
LIMITED_JWKS = "https://limited.facebook.com/.well-known/oauth/openid/jwks/"
LIMITED_ISSUERS = frozenset({"https://www.facebook.com"})


def appsecret_proof(token: str, secret: str) -> str:
    return hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()


def looks_like_jwt(token: str) -> bool:
    return token.count(".") == 2 and token.startswith("eyJ")


class FacebookProvider:
    name = "facebook"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        graph_version: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not app_id or not app_secret:
            raise ValueError("Facebook sign-in needs the app id and secret")
        self.app_id, self._secret, self.transport = app_id, app_secret, transport
        self.base = f"{GRAPH}/{graph_version}"
        self.jwks = JwksCache(self.name, LIMITED_JWKS, transport)

    async def verify(self, token: str, nonce: str) -> VerifiedIdentity:
        if looks_like_jwt(token):
            return await self._limited_login(token, nonce)
        return await self._access_token(token)

    async def _limited_login(self, token: str, nonce: str) -> VerifiedIdentity:
        claims = await verify_id_token(
            token, self.jwks, issuers=LIMITED_ISSUERS, audiences=[self.app_id], nonce=nonce,
            now=time.time(),
        )  # fmt: skip
        return _identity(str(claims["sub"]), claims.get("email"), claims.get("name"))

    async def _graph(self, path: str, params: dict[str, str]) -> Any:
        reply = await fetch_json(
            self.name, f"{self.base}/{path}", params=params, transport=self.transport
        )
        if reply.status != 200 or not isinstance(reply.body, dict):
            raise ProviderError()
        return reply.body

    async def _access_token(self, token: str) -> VerifiedIdentity:
        app_token = f"{self.app_id}|{self._secret}"
        debug = await self._graph("debug_token", {"input_token": token, "access_token": app_token})
        data = debug.get("data")
        if not isinstance(data, dict) or data.get("is_valid") is not True:
            raise ProviderError()
        if str(data.get("app_id")) != self.app_id or not data.get("user_id"):
            raise ProviderError()
        expires_at = int(data.get("expires_at") or 0)
        if expires_at and expires_at <= time.time():
            raise ProviderError()
        params = {"fields": "id,name,email", "access_token": token,
                  "appsecret_proof": appsecret_proof(token, self._secret)}  # fmt: skip
        me = await self._graph("me", params)
        if str(me.get("id")) != str(data["user_id"]):
            raise ProviderError()
        return _identity(str(me["id"]), me.get("email"), me.get("name"))


def _identity(subject: str, email: object, name: object) -> VerifiedIdentity:
    return VerifiedIdentity(
        provider="facebook",
        subject=subject,
        email=email.strip().lower() if isinstance(email, str) and email.strip() else None,
        email_verified=False,  # never auto-linked (05 §C.5 step 9)
        name=name if isinstance(name, str) else None,
    )

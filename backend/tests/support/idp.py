"""A fake OIDC IdP on an ``httpx.MockTransport``: discovery, authorise, token (PKCE-checked), JWKS."""

from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx

from app.core.security.oidc import OidcClient
from tests.support.oidc import id_token, jwks

ISSUER = "https://idp.example"
CLIENT_ID = "staff-client"
REDIRECT = "https://admin.example/sso/callback"
DOMAIN = "school.example"
EMAIL = f"ops@{DOMAIN}"


class FakeIdp:
    def __init__(self) -> None:
        self.claims: dict[str, Any] = {
            "amr": ["pwd", "mfa"],
            "email": EMAIL,
            "email_verified": True,
        }
        self.grants: dict[str, dict[str, str]] = {}
        self.token_status, self.down = 200, False
        self.client = OidcClient(ISSUER, CLIENT_ID, "staff-secret", transport=self.transport)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def authorize(self, location: str) -> tuple[str, str]:
        """Play the user signing in at the IdP; return ``(code, state)`` for the callback."""
        query = {k: v[0] for k, v in parse_qs(urlsplit(location).query).items()}
        code = secrets.token_urlsafe(16)
        self.grants[code] = query
        return code, query["state"]

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            return httpx.Response(503)
        path = request.url.path
        if path == "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}/authorize",
                "token_endpoint": f"{ISSUER}/token", "jwks_uri": f"{ISSUER}/jwks",
            })  # fmt: skip
        if path == "/jwks":
            return httpx.Response(200, json=jwks())
        return self.token(request)

    def token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        grant = self.grants.pop(form.get("code", ""), None)
        verifier = form.get("code_verifier", "").encode()
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier).digest()).rstrip(b"=")
        if (
            self.token_status != 200
            or grant is None
            or challenge.decode() != grant["code_challenge"]
        ):
            return httpx.Response(400, json={"error": "invalid_grant"})
        claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "idp-1", "nonce": grant["nonce"]}
        return httpx.Response(200, json={"id_token": id_token(**{**claims, **self.claims})})

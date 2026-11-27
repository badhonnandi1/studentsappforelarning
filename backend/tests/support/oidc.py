"""A local RSA key and JWKS for provider tests (no network)."""

from __future__ import annotations

import time
from functools import cache
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

KID = "test-kid-1"


@cache
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks() -> dict[str, Any]:
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(private_key().public_key(), as_dict=True)
    return {"keys": [{**jwk, "kid": KID, "alg": "RS256", "use": "sig"}]}


def id_token(*, kid: str = KID, alg: str = "RS256", **claims: Any) -> str:
    now = int(time.time())
    body = {"iat": now, "exp": now + 600, **claims}
    if alg == "HS256":
        return jwt.encode(body, "x" * 32, algorithm="HS256", headers={"kid": kid})
    return jwt.encode(body, private_key(), algorithm=alg, headers={"kid": kid})


def jwks_transport(calls: list[str], *, status: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, json=jwks(), headers={"Cache-Control": "max-age=600"})

    return httpx.MockTransport(handler)

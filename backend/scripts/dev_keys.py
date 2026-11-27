"""Print fresh local secrets for .env (never use these outside your machine)."""

from __future__ import annotations

import base64
import json
import secrets

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat


def ed25519_pem() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


def local_env() -> dict[str, str]:
    def token() -> str:
        return secrets.token_urlsafe(32)

    return {
        "JWT_PRIVATE_KEYS": json.dumps({"local-1": ed25519_pem()}),
        "JWT_ACTIVE_KID": "local-1",
        "OTP_HASH_KEY": token(),
        "PII_HASH_KEYS": json.dumps({p: token() for p in ("phone", "email", "ip", "device")}),
        "LOCAL_KMS_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
    }


if __name__ == "__main__":
    for name, value in local_env().items():
        print(f"{name}='{value}'")

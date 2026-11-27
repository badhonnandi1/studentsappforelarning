"""Deterministic-per-run test secrets, installed into the environment before ``app`` loads."""

from __future__ import annotations

import base64
import json
from collections.abc import MutableMapping

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat


def ed25519_pem() -> str:
    key = Ed25519PrivateKey.generate()
    return key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()


SECRET_VARS = (
    "JWT_PRIVATE_KEYS",
    "JWT_ACTIVE_KID",
    "OTP_HASH_KEY",
    "PII_HASH_KEYS",
    "LOCAL_KMS_KEY",
)


def install_test_keys(env: MutableMapping[str, str]) -> None:
    env.setdefault("JWT_PRIVATE_KEYS", json.dumps({"test-1": ed25519_pem()}))
    env.setdefault("JWT_ACTIVE_KID", "test-1")
    env.setdefault("OTP_HASH_KEY", "test-otp-key-" + "x" * 32)
    env.setdefault(
        "PII_HASH_KEYS",
        json.dumps({p: f"test-{p}-key-" + "y" * 32 for p in ("phone", "email", "ip", "device")}),
    )
    env.setdefault("LOCAL_KMS_KEY", base64.b64encode(b"k" * 32).decode())

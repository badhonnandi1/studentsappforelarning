"""Key management: wrap and unwrap data keys. AWS KMS in deployed envs, a local key otherwise."""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Protocol

import aioboto3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.settings import Settings


class KmsClient(Protocol):
    async def generate_data_key(self) -> tuple[bytes, bytes]:
        """Return ``(plaintext_key, wrapped_key)`` for a new 256-bit data key."""
        ...

    async def decrypt_data_key(self, wrapped: bytes) -> bytes: ...


class LocalKms:
    """AES-GCM key wrapping with a master key from ``LOCAL_KMS_KEY`` (local and test only)."""

    def __init__(self, master_key: bytes) -> None:
        if len(master_key) != 32:
            raise ValueError("local KMS master key must be 32 bytes")
        self._aead = AESGCM(master_key)

    @classmethod
    def from_settings(cls, settings: Settings) -> LocalKms:
        raw = settings.local_kms_key.get_secret_value()
        if raw:
            return cls(base64.b64decode(raw))
        return cls(hashlib.sha256(b"local-only-kms").digest())

    async def generate_data_key(self) -> tuple[bytes, bytes]:
        plaintext = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        return plaintext, nonce + self._aead.encrypt(nonce, plaintext, b"data-key")

    async def decrypt_data_key(self, wrapped: bytes) -> bytes:
        return self._aead.decrypt(wrapped[:12], wrapped[12:], b"data-key")


class AwsKms:  # pragma: no cover - exercised against real KMS in staging only
    def __init__(self, key_id: str, region: str) -> None:
        self.key_id, self.region = key_id, region
        self.session = aioboto3.Session()

    async def generate_data_key(self) -> tuple[bytes, bytes]:
        async with self.session.client("kms", region_name=self.region) as kms:
            response = await kms.generate_data_key(KeyId=self.key_id, KeySpec="AES_256")
        return response["Plaintext"], response["CiphertextBlob"]

    async def decrypt_data_key(self, wrapped: bytes) -> bytes:
        async with self.session.client("kms", region_name=self.region) as kms:
            response = await kms.decrypt(CiphertextBlob=wrapped, KeyId=self.key_id)
        plaintext: bytes = response["Plaintext"]
        return plaintext


def kms_from_settings(settings: Settings) -> KmsClient:
    if settings.kms_backend == "aws":  # pragma: no cover
        return AwsKms(settings.kms_key_id, settings.aws_region)
    return LocalKms.from_settings(settings)

"""Field-level envelope encryption for PII (``*_enc`` columns, 01 §1).

Each environment has one or more data keys, stored wrapped by KMS in ``PII_DATA_KEYS`` and
unwrapped once at startup. Ciphertext layout::

    version (1 byte = 1) | key id length (1) | key id | nonce (12) | AES-256-GCM ciphertext+tag

The key id in the header lets old rows decrypt after a new active key is introduced. The
column name is bound as associated data, so a phone ciphertext cannot be replayed as an email.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.security.kms import KmsClient, kms_from_settings
from app.core.settings import Settings

VERSION = 1
LOCAL_KEY_ID = "local"


class FieldCipher:
    def __init__(self, keys: dict[str, bytes], active: str) -> None:
        if active not in keys:
            raise ValueError("active data key is not loaded")
        self._keys = {kid: AESGCM(key) for kid, key in keys.items()}
        self.active = active

    def encrypt(self, plaintext: str, context: str) -> bytes:
        kid = self.active.encode()
        nonce = os.urandom(12)
        body = self._keys[self.active].encrypt(nonce, plaintext.encode(), context.encode())
        return bytes([VERSION, len(kid)]) + kid + nonce + body

    def decrypt(self, blob: bytes, context: str) -> str:
        if not blob or blob[0] != VERSION:
            raise ValueError("unknown ciphertext version")
        kid_len = blob[1]
        kid = blob[2 : 2 + kid_len].decode()
        nonce = blob[2 + kid_len : 14 + kid_len]
        aead = self._keys.get(kid)
        if aead is None:
            raise ValueError(f"data key {kid} is not loaded")
        return aead.decrypt(nonce, blob[14 + kid_len :], context.encode()).decode()

    @staticmethod
    def key_id(blob: bytes) -> str:
        return blob[2 : 2 + blob[1]].decode()


async def load_cipher(settings: Settings, kms: KmsClient | None = None) -> FieldCipher:
    kms = kms or kms_from_settings(settings)
    if not settings.pii_data_keys:
        if settings.is_deployed:  # pragma: no cover - refused by the settings validator
            raise RuntimeError("PII_DATA_KEYS is required")
        return FieldCipher({LOCAL_KEY_ID: hashlib.sha256(b"local-only-pii").digest()}, LOCAL_KEY_ID)
    keys = {
        kid: await kms.decrypt_data_key(base64.b64decode(wrapped))
        for kid, wrapped in settings.pii_data_keys.items()
    }
    return FieldCipher(keys, settings.pii_active_data_key)


_cipher: FieldCipher | None = None


async def init_crypto(settings: Settings, kms: KmsClient | None = None) -> FieldCipher:
    global _cipher
    _cipher = await load_cipher(settings, kms)
    return _cipher


def cipher() -> FieldCipher:
    if _cipher is None:
        raise RuntimeError("field encryption not initialised; call init_crypto() at startup")
    return _cipher


def encrypt_field(plaintext: str, context: str) -> bytes:
    return cipher().encrypt(plaintext, context)


def decrypt_field(blob: bytes, context: str) -> str:
    return cipher().decrypt(blob, context)

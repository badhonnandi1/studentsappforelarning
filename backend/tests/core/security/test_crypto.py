import base64

import pytest
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr

from app.core.security import crypto
from app.core.security.hashing import constant_time_equal, keyed_hash, otp_hash, sha256
from app.core.security.kms import LocalKms
from app.core.settings import Settings

pytestmark = pytest.mark.unit


async def cipher_with_two_keys() -> tuple[crypto.FieldCipher, LocalKms]:
    kms = LocalKms(b"m" * 32)
    _, wrapped1 = await kms.generate_data_key()
    _, wrapped2 = await kms.generate_data_key()
    settings = Settings(
        _env_file=None,
        pii_data_keys={
            "d1": base64.b64encode(wrapped1).decode(),
            "d2": base64.b64encode(wrapped2).decode(),
        },
        pii_active_data_key="d2",
    )
    return await crypto.load_cipher(settings, kms), kms


async def test_round_trip_and_key_id_header() -> None:
    cipher, _ = await cipher_with_two_keys()
    blob = cipher.encrypt("+8801712345678", "identity.users.phone")
    assert crypto.FieldCipher.key_id(blob) == "d2"
    assert cipher.decrypt(blob, "identity.users.phone") == "+8801712345678"
    assert b"8801712345678" not in blob


async def test_ciphertext_differs_per_call() -> None:
    cipher, _ = await cipher_with_two_keys()
    assert cipher.encrypt("x", "c") != cipher.encrypt("x", "c")


async def test_tampered_tag_and_wrong_context_fail() -> None:
    cipher, _ = await cipher_with_two_keys()
    blob = bytearray(cipher.encrypt("secret", "c"))
    blob[-1] ^= 1
    with pytest.raises(InvalidTag):
        cipher.decrypt(bytes(blob), "c")
    with pytest.raises(InvalidTag):
        cipher.decrypt(cipher.encrypt("secret", "phone"), "email")


async def test_old_key_still_decrypts_after_rotation() -> None:
    cipher, _ = await cipher_with_two_keys()
    cipher.active = "d1"
    blob = cipher.encrypt("old row", "c")
    cipher.active = "d2"
    assert cipher.decrypt(blob, "c") == "old row"


async def test_unknown_version_and_key() -> None:
    cipher, _ = await cipher_with_two_keys()
    with pytest.raises(ValueError, match="version"):
        cipher.decrypt(b"\x02abc", "c")
    with pytest.raises(ValueError, match="version"):
        cipher.decrypt(b"", "c")
    foreign = bytes([1, 2]) + b"zz" + b"\x00" * 30
    with pytest.raises(ValueError, match="not loaded"):
        cipher.decrypt(foreign, "c")
    with pytest.raises(ValueError, match="active"):
        crypto.FieldCipher({}, "x")


async def test_local_default_and_module_helpers() -> None:
    await crypto.init_crypto(Settings(_env_file=None))
    blob = crypto.encrypt_field("a@b.com", "identity.users.email")
    assert crypto.decrypt_field(blob, "identity.users.email") == "a@b.com"
    assert crypto.FieldCipher.key_id(blob) == crypto.LOCAL_KEY_ID


async def test_local_kms_wraps_and_unwraps() -> None:
    kms = LocalKms.from_settings(Settings(_env_file=None))
    plain, wrapped = await kms.generate_data_key()
    assert await kms.decrypt_data_key(wrapped) == plain
    assert isinstance(
        LocalKms.from_settings(Settings(_env_file=None, local_kms_key=SecretStr(""))), LocalKms
    )
    with pytest.raises(ValueError, match="32 bytes"):
        LocalKms(b"short")


@pytest.mark.usefixtures("no_env_secrets")
def test_keyed_hash_is_per_purpose_and_stable() -> None:
    keys = {p: SecretStr(f"{p}-" + "k" * 32) for p in ("phone", "email", "ip", "device")}
    settings = Settings(_env_file=None, pii_hash_keys=keys)
    phone = keyed_hash("+8801712345678", "phone", settings)
    assert phone == keyed_hash("+8801712345678", "phone", settings)
    assert phone != keyed_hash("+8801712345678", "email", settings)
    assert len(phone) == 32
    fallback = Settings(_env_file=None, pii_hash_keys={}, otp_hash_key=SecretStr(""))
    assert keyed_hash("x", "ip", fallback) != keyed_hash("x", "ip", settings)
    assert len(otp_hash("123456", "c1", fallback)) == 32


def test_otp_hash_is_bound_to_challenge() -> None:
    settings = Settings(_env_file=None)
    a = otp_hash("123456", "c1", settings)
    assert constant_time_equal(a, otp_hash("123456", "c1", settings))
    assert not constant_time_equal(a, otp_hash("123456", "c2", settings))
    assert sha256("x") == sha256(b"x")

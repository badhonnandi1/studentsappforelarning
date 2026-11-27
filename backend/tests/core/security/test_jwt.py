from datetime import UTC, datetime, timedelta

import jwt as pyjwt
import pytest
from pydantic import SecretStr

from app.core.errors import UnauthorizedError
from app.core.security.jwt import TokenKeys, init_token_keys, token_keys
from app.core.settings import Settings
from tests.support.keys import ed25519_pem

pytestmark = pytest.mark.unit
NOW = datetime(2026, 5, 1, 12, tzinfo=UTC)
TTL = timedelta(minutes=15)


def keys(active: str = "k1", **pems: str) -> TokenKeys:
    pems = pems or {"k1": ed25519_pem()}
    secret = {kid: SecretStr(pem) for kid, pem in pems.items()}
    return TokenKeys.from_settings(
        Settings(_env_file=None, jwt_private_keys=secret, jwt_active_kid=active)
    )


def test_sign_and_verify() -> None:
    k = keys()
    token = k.sign({"sub": "u1", "sid": "s1"}, audience="api", now=NOW, ttl=TTL)
    claims = k.verify(token, audience="api", now=NOW + timedelta(minutes=5))
    assert claims["sub"] == "u1"
    assert claims["aud"] == "api"
    assert pyjwt.get_unverified_header(token)["kid"] == "k1"


def test_wrong_audience() -> None:
    k = keys()
    token = k.sign({"sub": "u1"}, audience="api", now=NOW, ttl=TTL)
    with pytest.raises(UnauthorizedError):
        k.verify(token, audience="admin", now=NOW)


def test_expired_has_its_own_code() -> None:
    k = keys()
    token = k.sign({"sub": "u1"}, audience="api", now=NOW, ttl=TTL)
    with pytest.raises(UnauthorizedError) as caught:
        k.verify(token, audience="api", now=NOW + timedelta(minutes=16))
    assert caught.value.code == "token_expired"


def test_issued_in_the_future_rejected() -> None:
    k = keys()
    token = k.sign({"sub": "u1"}, audience="api", now=NOW + timedelta(minutes=5), ttl=TTL)
    with pytest.raises(UnauthorizedError):
        k.verify(token, audience="api", now=NOW)


def test_tampered_token_rejected() -> None:
    k = keys()
    token = k.sign({"sub": "u1"}, audience="api", now=NOW, ttl=TTL)
    head, _body, sig = token.split(".")
    forged = pyjwt.utils.base64url_encode(b'{"sub":"admin","aud":"api","iat":1,"exp":9999999999}')
    with pytest.raises(UnauthorizedError):
        k.verify(f"{head}.{forged.decode()}.{sig}", audience="api", now=NOW)
    with pytest.raises(UnauthorizedError):
        k.verify("not-a-jwt", audience="api", now=NOW)


def test_unknown_kid_and_other_key_rejected() -> None:
    token = keys().sign({"sub": "u1"}, audience="api", now=NOW, ttl=TTL)
    with pytest.raises(UnauthorizedError):
        keys().verify(token, audience="api", now=NOW)  # same kid name, different key
    other = keys(active="k9", k9=ed25519_pem())
    with pytest.raises(UnauthorizedError):
        other.verify(token, audience="api", now=NOW)


def test_rotation_with_two_kids() -> None:
    old, new = ed25519_pem(), ed25519_pem()
    before = keys("k1", k1=old)
    during = keys("k2", k1=old, k2=new)
    old_token = before.sign({"sub": "u"}, audience="api", now=NOW, ttl=TTL)
    new_token = during.sign({"sub": "u"}, audience="api", now=NOW, ttl=TTL)
    assert during.verify(old_token, audience="api", now=NOW)["sub"] == "u"
    assert pyjwt.get_unverified_header(new_token)["kid"] == "k2"


@pytest.mark.usefixtures("no_env_secrets")
def test_verify_only_with_public_keys() -> None:
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_pem_private_key,
    )

    pem = ed25519_pem()
    signer = keys("k1", k1=pem)
    public = (
        load_pem_private_key(pem.encode(), None)
        .public_key()
        .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    verifier = TokenKeys.from_settings(Settings(_env_file=None, jwt_public_keys={"k1": public}))
    token = signer.sign({"attempt_id": "a"}, audience="exam-ingest", now=NOW, ttl=TTL)
    assert verifier.verify(token, audience="exam-ingest", now=NOW)["attempt_id"] == "a"
    with pytest.raises(RuntimeError, match="no active"):
        verifier.sign({}, audience="api", now=NOW, ttl=TTL)


def test_module_level_keys() -> None:
    k = init_token_keys(Settings())
    assert token_keys() is k
    assert k.active == "test-1"


@pytest.mark.usefixtures("no_env_secrets")
def test_non_ed25519_keys_rejected() -> None:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )

    ec_key = ec.generate_private_key(ec.SECP256R1())
    private = ec_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()).decode()
    public = ec_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(ValueError, match="not Ed25519"):
        TokenKeys.from_settings(
            Settings(_env_file=None, jwt_private_keys={"e": SecretStr(private)})
        )
    with pytest.raises(ValueError, match="not Ed25519"):
        TokenKeys.from_settings(Settings(_env_file=None, jwt_public_keys={"e": public.decode()}))


def test_token_keys_before_init(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.security import jwt as jwt_module

    monkeypatch.setattr(jwt_module, "_keys", None)
    with pytest.raises(RuntimeError, match="not initialised"):
        token_keys()

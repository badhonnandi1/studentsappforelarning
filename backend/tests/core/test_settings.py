from typing import Any

import pytest
from pydantic import ValidationError

from app.core.settings import Settings

pytestmark = [pytest.mark.unit, pytest.mark.usefixtures("no_env_secrets")]

KEY = "k" * 32


def safe_prod(**overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "app_env": "prod",
        "cors_origins": ["https://app.example.com"],
        "exam_queue_backend": "sqs",
        "sms_backend": "http",
        "sms_api_url": "https://sms.example.com",
        "sms_api_key": KEY,
        "kms_backend": "aws",
        "otp_hash_key": KEY,
        "pii_hash_keys": dict.fromkeys(("phone", "email", "ip", "device"), KEY),
        "jwt_private_keys": {"k1": "pem"},
        "jwt_active_kid": "k1",
        "pii_data_keys": {"d1": "wrapped"},
        "pii_active_data_key": "d1",
        "staff_oidc_client_id": "client",
        "staff_oidc_client_secret": "secret",
        "staff_oidc_allowed_domains": ["example.com"],
        "staff_oidc_redirect_uris": ["https://admin.example.com/cb"],
        "test_phone_otp": "",
    }
    values.update(overrides)
    return values


def make(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


def test_local_defaults_load() -> None:
    settings = make(app_env="local", test_phone_otp="")
    assert settings.db_pool_mode == "direct"
    assert settings.facebook_graph_version == "v27.0"
    assert not settings.is_deployed


def test_safe_prod_config_loads() -> None:
    assert make(**safe_prod()).is_deployed


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"cors_origins": ["*"]}, "CORS_ORIGINS"),
        ({"sms_backend": "fake"}, "SMS_BACKEND"),
        ({"exam_queue_backend": "memory"}, "EXAM_QUEUE_BACKEND"),
        ({"kms_backend": "local"}, "KMS_BACKEND"),
        ({"debug": True}, "DEBUG"),
        ({"otp_hash_key": "short"}, "OTP_HASH_KEY"),
        ({"pii_hash_keys": {"phone": KEY}}, "PII_HASH_KEYS[email]"),
        ({"google_enabled": True}, "GOOGLE_CLIENT_IDS"),
        ({"facebook_enabled": True, "facebook_app_id": "1"}, "FACEBOOK_APP_SECRET"),
        ({"test_phone_otp": "123456"}, "TEST_PHONE_OTP"),
        ({"dev_staff_tokens": True}, "DEV_STAFF_TOKENS"),
        ({"staff_oidc_client_secret": ""}, "STAFF_OIDC_ISSUER"),
        ({"staff_oidc_allowed_domains": []}, "STAFF_OIDC_ALLOWED_DOMAINS"),
        ({"jwt_active_kid": "missing"}, "JWT_ACTIVE_KID"),
        ({"sms_api_key": ""}, "SMS_API_URL"),
        ({"pii_active_data_key": "nope"}, "PII_ACTIVE_DATA_KEY"),
    ],
)
def test_prod_refuses_unsafe(override: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message.replace("[", r"\[").replace("]", r"\]")):
        make(**safe_prod(**override))


def test_staging_uses_prod_rules() -> None:
    with pytest.raises(ValidationError):
        make(**safe_prod(app_env="staging", sms_backend="fake"))


def test_comma_lists_split() -> None:
    settings = make(app_env="local", cors_origins="https://a.com, https://b.com")
    assert settings.cors_origins == ["https://a.com", "https://b.com"]


def test_test_otp_only_local_and_test() -> None:
    assert make(app_env="test", test_phone_otp="123456").test_otp_allowed
    assert not make(app_env="test", test_phone_otp="").test_otp_allowed

"""Application settings from the environment (05 §C.13).

``get_settings()`` is cached. The validator refuses configurations that are unsafe outside
local and test environments, so a misconfigured deploy fails at boot instead of in production.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from app.core.settings_parts import (
    AuthSettings,
    CommaList,
    DbSettings,
    SocialSettings,
    StorageSettings,
    split_commas,
)

MIN_KEY_BYTES = 32
TEST_PHONE_FIRST = "+8801700000000"
TEST_PHONE_LAST = "+8801700009999"


class Settings(DbSettings, AuthSettings, SocialSettings, StorageSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    app_env: Literal["local", "test", "staging", "prod"] = "local"
    log_level: str = "INFO"
    log_json: bool = False
    debug: bool = False
    cors_origins: CommaList = Field(default_factory=list)
    min_app_version: str = "1.0.0"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        return split_commas(value)

    @property
    def is_deployed(self) -> bool:
        """Staging and prod get the same safety rules."""
        return self.app_env in ("staging", "prod")

    @property
    def test_otp_allowed(self) -> bool:
        return self.app_env in ("local", "test") and bool(self.test_phone_otp)

    @model_validator(mode="after")
    def _refuse_unsafe_deploy(self) -> Settings:
        if self.is_deployed:
            problems = deploy_problems(self)
            if problems:
                raise ValueError("unsafe configuration: " + "; ".join(problems))
        return self


def _short(secret: SecretStr) -> bool:
    return len(secret.get_secret_value().encode()) < MIN_KEY_BYTES


def deploy_problems(s: Settings) -> list[str]:
    """Every rule a staging or prod configuration must pass (05 §C.12, §C.13)."""
    problems: list[str] = []
    if s.debug:
        problems.append("DEBUG must be off")
    if "*" in s.cors_origins:
        problems.append("CORS_ORIGINS must list exact origins")
    if s.exam_queue_backend == "memory":
        problems.append("EXAM_QUEUE_BACKEND must be sqs")
    if s.sms_backend == "fake":
        problems.append("SMS_BACKEND must not be fake")
    if s.kms_backend == "local":
        problems.append("KMS_BACKEND must be aws")
    if s.test_phone_otp:
        problems.append("TEST_PHONE_OTP is only allowed in local and test")
    if s.dev_staff_tokens:
        problems.append("DEV_STAFF_TOKENS must be false")
    if _short(s.otp_hash_key):
        problems.append("OTP_HASH_KEY must be at least 32 bytes")
    for purpose in ("phone", "email", "ip", "device"):
        key = s.pii_hash_keys.get(purpose)
        if key is None or _short(key):
            problems.append(f"PII_HASH_KEYS[{purpose}] must be at least 32 bytes")
    if not s.jwt_private_keys or s.jwt_active_kid not in s.jwt_private_keys:
        problems.append("JWT_ACTIVE_KID must name a key in JWT_PRIVATE_KEYS")
    if s.google_enabled and not s.google_client_ids:
        problems.append("GOOGLE_CLIENT_IDS is required when Google is enabled")
    if s.facebook_enabled and (not s.facebook_app_id or _short(s.facebook_app_secret)):
        problems.append("FACEBOOK_APP_ID and FACEBOOK_APP_SECRET are required when enabled")
    staff = (s.staff_oidc_issuer, s.staff_oidc_client_id, s.staff_oidc_client_secret)
    if not all(v.get_secret_value() if isinstance(v, SecretStr) else v for v in staff):
        problems.append("STAFF_OIDC_ISSUER, _CLIENT_ID and _CLIENT_SECRET are required")
    if not s.staff_oidc_allowed_domains or not s.staff_oidc_redirect_uris:
        problems.append("STAFF_OIDC_ALLOWED_DOMAINS and _REDIRECT_URIS are required")
    if s.sms_backend == "http" and not (s.sms_api_url and s.sms_api_key.get_secret_value()):
        problems.append("SMS_API_URL and SMS_API_KEY are required for the http backend")
    return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()

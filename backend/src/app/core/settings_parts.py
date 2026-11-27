"""Setting groups, combined into ``Settings`` in settings.py.

Each group is a pydantic-settings class with flat environment names (05 §C.13), so the
environment stays ``DATABASE_URL`` rather than ``DB__URL``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode

CommaList = Annotated[list[str], NoDecode]


def split_commas(value: object) -> object:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


class DbSettings(BaseSettings):
    database_url: str = "postgresql+asyncpg://app_rw:app_rw@127.0.0.1:55432/studyplatform"
    database_migrator_url: str = (
        "postgresql+asyncpg://app_migrator:app_migrator@127.0.0.1:55432/studyplatform"
    )
    db_pool_mode: Literal["direct", "pgbouncer"] = "direct"
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_statement_timeout_ms: int = 5000
    db_lock_timeout_ms: int = 2000
    db_idle_in_transaction_timeout_ms: int = 10000
    redis_url: str = "redis://127.0.0.1:56379/0"


class AuthSettings(BaseSettings):
    jwt_private_keys: dict[str, SecretStr] = {}
    jwt_active_kid: str = ""
    otp_hash_key: SecretStr = SecretStr("")
    pii_hash_keys: dict[str, SecretStr] = {}
    kms_backend: Literal["aws", "local"] = "local"
    kms_key_id: str = "local"
    local_kms_key: SecretStr = SecretStr("")
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    staff_refresh_hours: int = 12
    max_sessions_per_user: int = 10
    test_phone_otp: str = ""


class SocialSettings(BaseSettings):
    google_enabled: bool = False
    google_client_ids: CommaList = []
    facebook_enabled: bool = False
    facebook_app_id: str = ""
    facebook_app_secret: SecretStr = SecretStr("")
    facebook_graph_version: str = "v27.0"
    staff_oidc_issuer: str = "https://accounts.google.com"
    staff_oidc_client_id: str = ""
    staff_oidc_client_secret: SecretStr = SecretStr("")
    staff_oidc_allowed_domains: CommaList = []
    staff_oidc_redirect_uris: CommaList = []
    dev_staff_tokens: bool = False

    @field_validator(
        "google_client_ids", "staff_oidc_allowed_domains", "staff_oidc_redirect_uris", mode="before"
    )
    @classmethod
    def _split(cls, value: object) -> object:
        return split_commas(value)


class StorageSettings(BaseSettings):
    s3_endpoint_url: str | None = "http://127.0.0.1:59000"
    s3_bucket_uploads: str = "studyplatform-uploads-local"
    s3_bucket_events: str = "studyplatform-events-local"
    aws_region: str = "ap-south-1"
    exam_queue_backend: Literal["sqs", "memory"] = "memory"
    sqs_exam_queue_url: str = ""
    sms_backend: Literal["fake", "http"] = "fake"
    sms_api_url: str = ""
    sms_api_key: SecretStr = SecretStr("")
    sms_sender_id: str = ""
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "studyplatform"

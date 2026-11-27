"""Environment-based settings shared by every entry point.

Values come from environment variables, then an optional ``.env`` file, then the
defaults below. The defaults are enough to start every entry point locally with
no cloud credentials.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_ignore_empty=True, extra="ignore"
    )

    app_env: Literal["local", "test", "staging", "prod"] = "local"
    log_level: str = "INFO"
    log_json: bool = True  # structlog JSON lines; set LOG_JSON=false for readable local logs

    # PostgreSQL 17 is the only system of record (v2 §0.2).
    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"

    # Redis: rate limits, quotas, leaderboards, exam locks, caches (v2 §0.2).
    redis_url: str = "redis://localhost:6379/0"

    # SQS Standard is reserved for exam-answer batches (v2 §0.2, C9).
    exam_answer_queue_backend: Literal["memory", "sqs"] = "memory"
    exam_answer_queue_url: str | None = None
    aws_region: str = "ap-south-1"

    # AI gateway provider (v2 §0.4). "none" means no provider calls.
    ai_provider: Literal["none", "anthropic"] = "none"
    anthropic_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.exam_answer_queue_backend == "sqs" and not self.exam_answer_queue_url:
            raise ValueError("EXAM_ANSWER_QUEUE_URL is required when EXAM_ANSWER_QUEUE_BACKEND=sqs")
        if self.app_env in ("staging", "prod") and self.exam_answer_queue_backend == "memory":
            raise ValueError("The in-memory exam answer queue is for local/test only; use sqs")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

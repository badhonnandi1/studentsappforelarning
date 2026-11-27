import os

# Tests need no database, Redis or cloud credentials. Point the data stores at a
# closed port so readiness checks fail fast and deterministically. This must run
# before any app module loads settings.
os.environ.update(
    APP_ENV="test",
    LOG_JSON="false",
    DATABASE_URL="postgresql+psycopg://app:app@127.0.0.1:1/app",
    REDIS_URL="redis://127.0.0.1:1/0",
    EXAM_ANSWER_QUEUE_BACKEND="memory",
)

import pytest

CLOUD_VARS = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def clean_env() -> dict[str, str]:
    """Environment for subprocesses: test settings and no cloud credentials."""
    return {k: v for k, v in os.environ.items() if k not in CLOUD_VARS}

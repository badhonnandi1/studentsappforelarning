import subprocess
import sys

import pytest

PYTHON = sys.executable


@pytest.mark.parametrize("module", ["app.entrypoints.workers", "app.entrypoints.exam_consumers"])
def test_startup_check_exits_cleanly(module: str, clean_env: dict[str, str]) -> None:
    result = subprocess.run(
        [PYTHON, "-m", module, "--check"], env=clean_env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert "startup check ok" in result.stderr


def test_startup_check_fails_on_bad_config(clean_env: dict[str, str]) -> None:
    env = clean_env | {"EXAM_ANSWER_QUEUE_BACKEND": "sqs", "EXAM_ANSWER_QUEUE_URL": ""}
    result = subprocess.run(
        [PYTHON, "-m", "app.entrypoints.exam_consumers", "--check"],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1
    assert "EXAM_ANSWER_QUEUE_URL is required" in result.stderr

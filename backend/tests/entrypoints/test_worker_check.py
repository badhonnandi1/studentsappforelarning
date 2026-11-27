"""``--check`` on the worker deployables: exit 0 when healthy, 1 on a bad configuration."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration


def run(module: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, "--check", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=60,
    )


WORKERS = "app.entrypoints.workers.main"
CONSUMERS = "app.entrypoints.exam_consumers.main"


def test_workers_check_ok(deploy_env: dict[str, str]) -> None:
    result = run(WORKERS, deploy_env, "--queues", "sms,maintenance,default")
    assert result.returncode == 0, result.stderr
    assert "workers check ok" in result.stdout


def test_workers_check_unknown_queue(deploy_env: dict[str, str]) -> None:
    result = run(WORKERS, deploy_env, "--queues", "default,nope")
    assert result.returncode == 1
    assert "unknown queue: nope" in result.stderr


def test_workers_check_unreachable_database(deploy_env: dict[str, str]) -> None:
    env = {**deploy_env, "DATABASE_URL": "postgresql+asyncpg://app_rw:x@127.0.0.1:1/none"}
    result = run(WORKERS, env)
    assert result.returncode == 1
    assert "db is unreachable" in result.stderr


@pytest.mark.parametrize("module", [WORKERS, CONSUMERS])
def test_unsafe_deploy_config_exits_1(deploy_env: dict[str, str], module: str) -> None:
    result = run(module, {**deploy_env, "APP_ENV": "prod"})
    assert result.returncode == 1
    assert "invalid configuration" in result.stderr


def test_exam_consumers_check(deploy_env: dict[str, str]) -> None:
    ok = run(CONSUMERS, deploy_env)
    assert ok.returncode == 0, ok.stderr
    sqs = {**deploy_env, "EXAM_QUEUE_BACKEND": "sqs"}
    bad = run(CONSUMERS, {**sqs, "SQS_EXAM_QUEUE_URL": "http://queue"})
    assert bad.returncode == 1
    assert "SQS_EXAM_QUEUE_URL" in bad.stderr
    url = "https://sqs.ap-south-1.amazonaws.com/123456789012/exam-answers"
    good = run(CONSUMERS, {**sqs, "SQS_EXAM_QUEUE_URL": url})
    assert good.returncode == 0, good.stderr

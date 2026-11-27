"""Exam consumers: ``python -m app.entrypoints.exam_consumers.main``.

A skeleton until B5 adds the SQS loop. ``--check`` validates the queue settings.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from urllib.parse import urlparse

import structlog
from pydantic import ValidationError

from app.core.redis import close_redis
from app.core.settings import Settings, get_settings
from app.entrypoints.boot import configure_process, install_stop_signals

log = structlog.get_logger("app.exam_consumers")


def sqs_problems(settings: Settings) -> list[str]:
    if settings.exam_queue_backend == "memory":
        return []  # refused outside local and test by the settings validator
    url = urlparse(settings.sqs_exam_queue_url)
    parts = [p for p in url.path.split("/") if p]
    if url.scheme != "https" or not url.netloc or len(parts) != 2:
        return ["SQS_EXAM_QUEUE_URL must be https://<host>/<account>/<queue>"]
    if not settings.aws_region:
        return ["AWS_REGION is required for SQS"]
    return []


async def run() -> None:
    configure_process(get_settings(), "exam-consumers")
    stop = asyncio.Event()
    install_stop_signals(stop)
    log.info("exam_consumers_started", note="consumer loop arrives in B5")
    try:
        await stop.wait()
    finally:
        await close_redis()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exam-consumers")
    parser.add_argument("--check", action="store_true", help="validate and exit")
    args = parser.parse_args(argv)
    try:
        settings = get_settings()
    except ValidationError as exc:
        sys.stderr.write(f"invalid configuration: {exc}\n")
        return 1
    if args.check:
        problems = sqs_problems(settings)
        sys.stderr.writelines(f"{p}\n" for p in problems)
        if not problems:
            sys.stdout.write("exam-consumers check ok\n")
        return 1 if problems else 0
    asyncio.run(run())
    return 0


if __name__ == "__main__":
    sys.exit(main())

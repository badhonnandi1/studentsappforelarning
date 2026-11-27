"""Job worker: ``python -m app.entrypoints.workers.main --queues sms,maintenance,default``.

Runs the job worker, the outbox relay loop and the periodic scheduler. ``--check`` validates
the configuration, the queues and the handler registry, and that Postgres and Redis answer.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from pydantic import ValidationError

from app.core.db import sessionmaker
from app.core.http import run_ready_checks
from app.core.settings import Settings, get_settings
from app.core.storage import Storage
from app.entrypoints.boot import install_stop_signals
from app.entrypoints.stack import READY_CHECKS, start_stack, stop_stack
from app.modules import nfr
from app.modules.registry import all_job_handlers

DEFAULT_QUEUES = "sms,maintenance,default"


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="workers")
    parser.add_argument("--queues", default=DEFAULT_QUEUES)
    parser.add_argument("--no-relay", action="store_true", help="do not run the outbox relay")
    parser.add_argument("--check", action="store_true", help="validate and exit")
    return parser.parse_args(argv)


async def check(settings: Settings, queues: tuple[str, ...]) -> list[str]:
    problems = [f"unknown queue: {q}" for q in nfr.unknown_queues(queues)]
    handlers = all_job_handlers()
    problems += [f"no handler for periodic job: {k}" for k in nfr.missing_handlers(handlers)]
    await start_stack(settings, "workers", "worker")
    try:
        problems += [f"{name} is unreachable" for name in await run_ready_checks(READY_CHECKS)]
    finally:
        await stop_stack()
    return problems


async def run(settings: Settings, queues: tuple[str, ...], relay: bool) -> None:
    await start_stack(settings, "workers", "worker")
    stop = asyncio.Event()
    install_stop_signals(stop)
    target = nfr.RelayTarget(Storage(settings), settings.s3_bucket_events) if relay else None
    try:
        await nfr.run_worker_process(sessionmaker(), all_job_handlers(), queues, stop, relay=target)
    finally:
        await stop_stack()


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    try:
        settings = get_settings()
    except ValidationError as exc:
        sys.stderr.write(f"invalid configuration: {exc}\n")
        return 1
    queues = tuple(q.strip() for q in args.queues.split(",") if q.strip())
    if args.check:
        problems = asyncio.run(check(settings, queues))
        sys.stderr.writelines(f"{p}\n" for p in problems)
        if not problems:
            sys.stdout.write("workers check ok\n")
        return 1 if problems else 0
    asyncio.run(run(settings, queues, relay=not args.no_relay))
    return 0


if __name__ == "__main__":
    sys.exit(main())

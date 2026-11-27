"""exam-consumers deployable: SQS answer-batch consumers and scorer (v2 §2.1, §6.2).

Reads exam-answer batches from the queue and writes the append-only batch log and
latest-answer table in PostgreSQL (app.modules.exam.consumers).

Run: uv run exam-consumers            (idle loop until Ctrl+C)
     uv run exam-consumers --check    (startup check, then exit)
"""

import sys

from app.core.db import get_engine
from app.core.settings import Settings
from app.core.worker import run_worker
from app.modules.exam.ingest.queue import build_queue


def startup_check(settings: Settings) -> dict[str, object]:
    engine = get_engine()  # does not connect
    queue = build_queue(settings)
    return {
        "env": settings.app_env,
        "database": engine.url.render_as_string(hide_password=True),
        "answer_queue": queue.name,
    }


def main(argv: list[str] | None = None) -> int:
    return run_worker("exam-consumers", startup_check, argv)


if __name__ == "__main__":
    sys.exit(main())

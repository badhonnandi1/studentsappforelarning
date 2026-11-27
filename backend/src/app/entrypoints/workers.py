"""workers deployable: Postgres job runner (v2 §2.1).

Runs the outbox relay, leaderboards, imports and OCR, notifications,
reconciliation and rescoring from the Postgres job queue (app.modules.nfr.jobqueue).

Run: uv run workers            (idle loop until Ctrl+C)
     uv run workers --check    (startup check, then exit)
"""

import sys

from app.core.db import get_engine
from app.core.settings import Settings
from app.core.worker import run_worker
from app.modules.nfr import jobqueue


def startup_check(settings: Settings) -> dict[str, object]:
    engine = get_engine()  # builds the engine and loads the driver; does not connect
    return {
        "env": settings.app_env,
        "database": engine.url.render_as_string(hide_password=True),
        "job_handlers": sorted(jobqueue.HANDLERS),
    }


def main(argv: list[str] | None = None) -> int:
    return run_worker("workers", startup_check, argv)


if __name__ == "__main__":
    sys.exit(main())

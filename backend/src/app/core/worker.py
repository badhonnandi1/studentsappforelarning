"""Shared command-line runner for the non-HTTP deployables (workers, exam-consumers).

``--check`` runs the startup check and exits 0 (or 1 on failure). Without it the
process runs the same check and then idles until SIGINT/SIGTERM, because no job
handlers exist yet.
"""

import argparse
import logging
import signal
import threading
from collections.abc import Callable

from app.core.logging import configure_logging
from app.core.settings import Settings, get_settings

StartupCheck = Callable[[Settings], dict[str, object]]


def run_worker(name: str, startup_check: StartupCheck, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=name)
    parser.add_argument("--check", action="store_true", help="run the startup check and exit")
    args = parser.parse_args(argv)

    log = logging.getLogger(name)
    try:
        settings = get_settings()
        configure_logging(json=settings.log_json, level=settings.log_level)
        summary = startup_check(settings)
    except Exception as exc:  # report any config or import problem and fail
        configure_logging(json=False)
        log.error("startup check failed: %s", exc)
        return 1

    log.info("startup check ok: %s", summary)
    if args.check:
        return 0

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    log.info("running; no handlers registered yet. Ctrl+C to stop.")
    while not stop.wait(timeout=5.0):
        pass
    log.info("stopped cleanly")
    return 0

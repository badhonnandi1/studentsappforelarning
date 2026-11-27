import asyncio
import os
import signal

import pytest

from app.entrypoints.boot import install_stop_signals

pytestmark = pytest.mark.integration


async def test_sigterm_sets_stop() -> None:
    stop = asyncio.Event()
    install_stop_signals(stop)
    loop = asyncio.get_running_loop()
    try:
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(stop.wait(), 5)
    finally:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.remove_signal_handler(sig)

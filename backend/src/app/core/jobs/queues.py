"""The canonical queue list (R-04). Standard library only, so migrations can import it.

No other queue name may appear in code or documents; the ``platform.jobs.queue`` CHECK is built
from this tuple and ``tests/contract/test_job_queues.py`` asserts the two match.
"""

from __future__ import annotations

QUEUES: tuple[str, ...] = (
    "default",
    "relay",
    "notify",
    "sms",
    "gam",
    "rescoring",
    "imports",
    "ai",
    "exam",
    "campaign",
    "payments",
    "maintenance",
)
PRIORITY_MIN, PRIORITY_MAX = -100, 100
OTP_PRIORITY = 100

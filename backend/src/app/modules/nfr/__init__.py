"""NFR (platform): platform-wide services: jobs, outbox, idempotency, runtime config.

Public API of the module. Other modules import only from here and from ``contracts``.
"""

from __future__ import annotations

from typing import Any

from app.modules.nfr.contracts.events import EventEnvelope, register_payload
from app.modules.nfr.contracts.jobs import JobContext, JobHandler
from app.modules.nfr.internal.services.consumer import consumer
from app.modules.nfr.internal.services.enqueue import enqueue
from app.modules.nfr.internal.services.idempotency import Idem, idempotent
from app.modules.nfr.internal.services.publish import make_event, publish
from app.modules.nfr.internal.services.runtime_config import (
    get_value as get_runtime_flag,
)
from app.modules.nfr.internal.services.runtime_config import (
    invalidate as invalidate_runtime_config,
)
from app.modules.nfr.internal.services.runtime_config import (
    require_enabled,
)
from app.modules.nfr.internal.services.runtime_config import (
    set_value as set_runtime_value,
)
from app.modules.nfr.internal.services.scheduler import Periodic, register_periodic

CODE = "NFR"
SCHEMA = "platform"

__all__ = [
    "CODE",
    "SCHEMA",
    "EventEnvelope",
    "Idem",
    "JobContext",
    "JobHandler",
    "Periodic",
    "consumer",
    "enqueue",
    "get_runtime_flag",
    "idempotent",
    "invalidate_runtime_config",
    "job_handlers",
    "make_event",
    "publish",
    "register_payload",
    "register_periodic",
    "require_enabled",
    "routers",
    "set_runtime_value",
]


def routers() -> list[Any]:
    from app.modules.nfr.internal.routes.config import router

    return [router]


def job_handlers() -> dict[str, JobHandler]:
    from app.modules.nfr.internal.jobs import partition_maintenance, retention
    from app.modules.nfr.internal.services.consumer import consumer_job_handlers

    return {
        "platform.partition.maintain": partition_maintenance.handle,
        "platform.retention.purge": retention.handle,
        **consumer_job_handlers(),
    }

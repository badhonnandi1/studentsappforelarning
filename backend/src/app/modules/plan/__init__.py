"""PLAN (notify): notifications and SMS. Public API of the module (SMS only in B1)."""

from __future__ import annotations

from typing import Any

from app.modules.plan.internal.services.send import JOB_KIND, Purpose, send_sms

CODE = "PLAN"
SCHEMA = "notify"

__all__ = ["CODE", "SCHEMA", "Purpose", "job_handlers", "send_sms"]


def job_handlers() -> dict[str, Any]:
    from app.modules.plan.internal.jobs.sms_send import handler

    return {JOB_KIND: handler}

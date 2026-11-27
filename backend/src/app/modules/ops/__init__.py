"""OPS (ops): audit log, runtime config admin and operations. Public API of the module.

OPS is a leaf (04 §4 R-03): it depends only on NFR and core.
"""

from __future__ import annotations

from typing import Any

from app.modules.ops.contracts.audit import AuditActor, AuditTarget
from app.modules.ops.internal.services.audited import AuditRecord, audited

CODE = "OPS"
SCHEMA = "ops"

__all__ = ["CODE", "SCHEMA", "AuditActor", "AuditRecord", "AuditTarget", "audited", "routers"]


def routers() -> list[Any]:
    from app.modules.ops.internal.routes.admin_audit import router

    return [router]

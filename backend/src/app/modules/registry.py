"""The 16 server modules, their database schemas and their public hooks (04 §2, 01 §2).

OFF (offline) is client-only and has no package. ``b01_01`` creates exactly the schemas listed
here, and ``tests/modules/test_registry.py`` keeps the two in step.

Modules are imported lazily by dotted path so this file stays a plain list: adding a module is
one line here plus its package.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import ModuleType
from typing import Any


@dataclass(frozen=True)
class ModuleInfo:
    code: str
    package: str
    schema: str
    build: int

    @property
    def dotted(self) -> str:
        return f"app.modules.{self.package}"


MODULES: tuple[ModuleInfo, ...] = (
    ModuleInfo("NFR", "nfr", "platform", 1),
    ModuleInfo("AUTH", "auth", "identity", 1),
    ModuleInfo("COM", "com", "community", 1),
    ModuleInfo("PLAN", "plan", "notify", 1),
    ModuleInfo("OPS", "ops", "ops", 1),
    ModuleInfo("TAX", "tax", "curriculum", 2),
    ModuleInfo("QB", "qb", "qbank", 2),
    ModuleInfo("CMS", "cms", "cms", 2),
    ModuleInfo("PRAC", "prac", "practice", 3),
    ModuleInfo("EXAM", "exam", "exam", 5),
    ModuleInfo("ANL", "anl", "analytics", 3),
    ModuleInfo("AI", "ai", "ai", 4),
    ModuleInfo("GAM", "gam", "rewards", 3),
    ModuleInfo("PAY", "pay", "commerce", 6),
    ModuleInfo("INST", "inst", "institution", 8),
    ModuleInfo("PAR", "par", "parent", 6),
)

SCHEMAS: tuple[str, ...] = tuple(m.schema for m in MODULES)


def load(module: ModuleInfo) -> ModuleType:
    return importlib.import_module(module.dotted)


def load_models() -> None:
    """Import every module's ORM models so ``Base.metadata`` is complete (Alembic, tests)."""
    for module in MODULES:
        try:
            importlib.import_module(f"{module.dotted}.internal.models")
        except ModuleNotFoundError as exc:
            if exc.name != f"{module.dotted}.internal.models":
                raise


def _collect(hook: str) -> Iterable[Any]:
    for module in MODULES:
        fn: Callable[[], Iterable[Any]] | None = getattr(load(module), hook, None)
        if fn is not None:
            yield from fn()


def run_startup() -> None:
    """Call each module's ``startup()`` (after the engine exists); e.g. AUTH's grants loader."""
    for module in MODULES:
        fn: Callable[[], None] | None = getattr(load(module), "startup", None)
        if fn is not None:
            fn()


def all_routers() -> list[Any]:
    return list(_collect("routers"))


def all_job_handlers() -> dict[str, Any]:
    handlers: dict[str, Any] = {}
    for module in MODULES:
        fn = getattr(load(module), "job_handlers", None)
        if fn is None:
            continue
        for kind, handler in fn().items():
            if kind in handlers:
                raise ValueError(f"job kind {kind} registered twice")
            handlers[kind] = handler
    return handlers

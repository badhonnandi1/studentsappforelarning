"""OPS fixtures: a fake grants loader and fresh runtime-config caches."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest

from app.core import ratelimit
from app.core.security import actor as actor_mod
from app.core.security.actor import Grant
from app.modules.nfr.internal.services import runtime_config

AUDITOR = uuid.UUID("00000000-0000-7000-8000-0000000000a1")
OPERATOR = uuid.UUID("00000000-0000-7000-8000-0000000000a2")
GRANTS = {AUDITOR: [Grant("audit.read")], OPERATOR: [Grant("audit.read"), Grant("ops.config")]}


async def loader(user_id: uuid.UUID) -> list[Grant]:
    return GRANTS.get(user_id, [])


@pytest.fixture(autouse=True)
def grants_and_config() -> Iterator[None]:
    actor_mod.set_grants_loader(loader)
    runtime_config._cache = None
    yield
    actor_mod.set_grants_loader(None)
    runtime_config._cache = None
    ratelimit.set_tier_overrides({})

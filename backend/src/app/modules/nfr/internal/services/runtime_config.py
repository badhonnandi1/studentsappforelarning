"""Runtime flags (kill switches, minimum app versions, support links, rate-limit overrides).

Reads go process cache (30 s) → Redis ``cfg:runtime`` (30 s) → Postgres. Writes go through OPS
``audited`` (step 6) and invalidate both caches. Every key has a schema and a default here; a key
outside this allow-list cannot be written.
"""

from __future__ import annotations

import contextlib
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

import structlog
from pydantic import Field, TypeAdapter, ValidationError
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.errors import UnavailableError, ValidationAppError
from app.core.redis import get_json, get_redis, set_json
from app.modules.nfr.internal.models import RuntimeConfig

log = structlog.get_logger(__name__)
CACHE_KEY, TTL_S = "cfg:runtime", 30
SemVer = Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$")]


@dataclass(frozen=True)
class ConfigKey:
    key: str
    adapter: TypeAdapter[Any]
    default: Any
    description: str


def _key(key: str, kind: Any, default: Any, description: str) -> ConfigKey:
    return ConfigKey(key, TypeAdapter(kind), default, description)


RuleSpec = dict[str, list[dict[str, Any]]]
KEYS: dict[str, ConfigKey] = {
    k.key: k
    for k in (
        _key("kill.tutor", bool, False, "Turn the AI tutor off"),
        _key("kill.photo_solve", bool, False, "Turn photo solve off"),
        _key("kill.registrations", bool, False, "Refuse new sign-ups"),
        _key("kill.payments", bool, False, "Refuse new payments"),
        _key("min_app_version.android", SemVer, "1.0.0", "Oldest Android app allowed"),
        _key("min_app_version.web", SemVer, "1.0.0", "Oldest web app allowed"),
        _key("support.links", dict[str, str], {}, "Support contact links shown in the app"),
        _key("ratelimit.overrides", RuleSpec, {}, "Per-tier rate-limit rules (14 §1.7)"),
    )
}

_cache: tuple[float, dict[str, Any]] | None = None


def defaults() -> dict[str, Any]:
    return {k.key: k.default for k in KEYS.values()}


def validate(key: str, value: Any) -> Any:
    spec = KEYS.get(key)
    if spec is None:
        raise ValidationAppError("Unknown runtime config key", details={"key": key})
    try:
        checked = spec.adapter.validate_python(value)
        if key == "ratelimit.overrides":
            parse_overrides(checked)
    except (ValidationError, KeyError, TypeError, ValueError) as exc:
        raise ValidationAppError("Invalid value for this key", details={"key": key}) from exc
    return checked


def parse_overrides(spec: RuleSpec) -> dict[str, ratelimit.Tier]:
    tiers = {}
    for name, rules in spec.items():
        base = ratelimit.TIERS[name]
        parsed = tuple(
            ratelimit.Rule(str(r["scope"]), int(r["limit"]), int(r["window_s"])) for r in rules
        )
        tiers[name] = ratelimit.Tier(name, parsed, fail_open=base.fail_open)
    return tiers


def _apply(values: dict[str, Any]) -> dict[str, Any]:
    global _cache
    _cache = (time.monotonic() + TTL_S, values)
    ratelimit.set_tier_overrides(parse_overrides(values.get("ratelimit.overrides") or {}))
    return values


async def load_all(session: AsyncSession) -> dict[str, Any]:
    if _cache is not None and _cache[0] > time.monotonic():
        return _cache[1]
    try:
        cached = await get_json(CACHE_KEY)
        if isinstance(cached, dict):
            return _apply({**defaults(), **cached})
    except (RedisError, OSError):
        log.warning("runtime_config_cache_unavailable")
    opened = not session.in_transaction()
    rows = (await session.execute(select(RuntimeConfig.key, RuntimeConfig.value))).all()
    if opened:
        await session.commit()  # end the read-only transaction so callers can begin() after
    values = {**defaults(), **{key: value for key, value in rows if key in KEYS}}
    with contextlib.suppress(RedisError, OSError):
        await set_json(CACHE_KEY, values, TTL_S)
    return _apply(values)


async def get_value(session: AsyncSession, key: str) -> Any:
    if key not in KEYS:
        raise KeyError(key)
    return (await load_all(session))[key]


async def is_killed(session: AsyncSession, feature: str) -> bool:
    return bool(await get_value(session, f"kill.{feature}"))


async def require_enabled(session: AsyncSession, feature: str) -> None:
    if await is_killed(session, feature):
        raise UnavailableError("This feature is switched off for now", code="kill_switch")


async def invalidate() -> None:
    global _cache
    _cache = None
    try:
        await get_redis().delete(CACHE_KEY)
    except (RedisError, OSError):
        log.warning("runtime_config_invalidate_failed")


async def set_value(
    session: AsyncSession, key: str, value: Any, *, actor_id: uuid.UUID | None, now: datetime
) -> tuple[Any, Any]:
    """Upsert in the caller's transaction; return ``(before, after)`` for the audit diff.

    Callers invalidate the caches after commit (``invalidate``).
    """
    checked = validate(key, value)
    row = await session.get(RuntimeConfig, key, with_for_update=True)
    before = row.value if row is not None else KEYS[key].default
    values = {"value": checked, "updated_at": now, "updated_by": actor_id}
    stmt = insert(RuntimeConfig).values(key=key, description=KEYS[key].description, **values)
    await session.execute(stmt.on_conflict_do_update(index_elements=["key"], set_=values))
    return before, checked

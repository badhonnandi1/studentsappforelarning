"""``Idempotency-Key`` handling for POSTs (14 §1.6, v2 §3.5).

Usage in a route::

    @router.post("/things", status_code=201)
    async def create(body: In, idem: Idem = Depends(idempotent("things.create", user=user_id))):
        if idem.replay is not None:
            return idem.replay
        async with session.begin():  # the record commits with the resource it describes
            thing = await service.create(session, ...)
            return await idem.respond(201, ThingOut.model_validate(thing), resource_id=thing.id)

A completed key replays the stored status and body with ``Idempotent-Replay: true``. The same key
with a different body is ``422 idempotency_key_reused``. While a request with the key is in
flight, a second one gets ``409 conflict`` (Redis ``SETNX``, safe to lose). Keys are per user.
"""

import contextlib
import hashlib
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

import structlog
from fastapi import Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from redis.exceptions import RedisError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ConflictError, ValidationAppError
from app.core.redis import get_redis
from app.modules.nfr.internal.repositories import idempotency as repo

log = structlog.get_logger(__name__)
LOCK_TTL_S = 30
MAX_STORED_BYTES = 64 * 1024
ReplayReader = Callable[[AsyncSession, uuid.UUID], Awaitable[Any]]


def request_hash(method: str, route: str, body: bytes) -> bytes:
    try:
        canonical = json.dumps(json.loads(body or b"null"), sort_keys=True, separators=(",", ":"))
    except ValueError:
        canonical = body.decode(errors="replace")
    return hashlib.sha256(f"{method}\n{route}\n{canonical}".encode()).digest()


def replay_response(status_code: int, body: Any) -> JSONResponse:
    return JSONResponse(body, status_code=status_code, headers={"Idempotent-Replay": "true"})


class Idem:
    def __init__(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        key: uuid.UUID | None,
        method: str,
        route: str,
        digest: bytes,
    ) -> None:
        self.session, self.user_id, self.key = session, user_id, key
        self.method, self.route, self.digest = method, route, digest
        self.replay: Response | None = None

    async def record(self, status_code: int, body: Any, resource_id: uuid.UUID | None) -> Any:
        """Store the outcome in the current transaction; return the JSON-ready body."""
        encoded = jsonable_encoder(body)
        if self.key is None:
            return encoded
        too_big = len(json.dumps(encoded)) > MAX_STORED_BYTES and resource_id is not None
        await repo.store_response(
            self.session,
            user_id=self.user_id,
            key=self.key,
            request_hash=self.digest,
            method=self.method,
            route=self.route,
            status_code=status_code,
            response=None if too_big else encoded,
            resource_id=resource_id,
        )
        return encoded

    async def respond(
        self, status_code: int, body: Any, *, resource_id: uuid.UUID | None = None
    ) -> JSONResponse:
        if self.session.in_transaction():
            encoded = await self.record(status_code, body, resource_id)
        else:
            async with self.session.begin():
                encoded = await self.record(status_code, body, resource_id)
        return JSONResponse(encoded, status_code=status_code)


async def _lock(lock_key: str) -> bool:
    try:
        return bool(await get_redis().set(lock_key, "1", nx=True, ex=LOCK_TTL_S))
    except (RedisError, OSError):
        log.warning("idempotency_lock_unavailable")
        return True


async def _unlock(lock_key: str) -> None:
    with contextlib.suppress(RedisError, OSError):
        await get_redis().delete(lock_key)


def idempotent(
    route_id: str,
    *,
    user: Callable[..., Any],
    required: bool = True,
    reread: ReplayReader | None = None,
) -> Callable[..., AsyncIterator[Idem]]:
    """``user`` is a dependency returning the caller's user id (or device-scope UUID)."""

    async def dependency(
        request: Request,
        user_id: Annotated[uuid.UUID, Depends(user)],
        session: Annotated[AsyncSession, Depends(get_session)],
        idempotency_key: Annotated[uuid.UUID | None, Header()] = None,
    ) -> AsyncIterator[Idem]:
        if idempotency_key is None and required:
            raise ValidationAppError("Idempotency-Key header is required", code="validation_error")
        digest = request_hash(request.method, route_id, await request.body())
        idem = Idem(session, user_id, idempotency_key, request.method, route_id, digest)
        if idempotency_key is None:
            yield idem
            return
        existing = await repo.get(session, user_id, idempotency_key)
        if session.in_transaction():
            await session.commit()  # end the read-only transaction the lookup opened
        if existing is not None and existing.status_code is not None:
            if existing.request_hash != digest:
                raise ValidationAppError(
                    "Idempotency-Key was used with a different request",
                    code="idempotency_key_reused",
                )
            body = existing.response
            if body is None and reread is not None and existing.resource_id is not None:
                body = jsonable_encoder(await reread(session, existing.resource_id))
            idem.replay = replay_response(existing.status_code, body)
            yield idem
            return
        lock_key = f"idem:lock:{user_id}:{idempotency_key}"
        if not await _lock(lock_key):
            raise ConflictError("A request with this Idempotency-Key is in progress")
        try:
            yield idem
        finally:
            await _unlock(lock_key)

    return dependency

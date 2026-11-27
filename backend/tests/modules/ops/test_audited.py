"""``audited()``: one transaction with the change, diff only, PII redacted, append-only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.core.security.actor import Actor
from app.core.security.hashing import keyed_hash
from app.modules import ops
from app.modules.ops.internal.models import AuditLog
from app.modules.ops.internal.services.audited import changed, needs_reason, redact

pytestmark = pytest.mark.db
STAFF = Actor(uuid.uuid4(), uuid.uuid4(), frozenset({"ops_admin"}), audience="admin", sso=True)
TARGET = ops.AuditTarget(type="user", id="u-1")


async def count(session: AsyncSession) -> int:
    return int((await session.execute(select(func.count()).select_from(AuditLog))).scalar_one())


async def test_row_written_with_the_change(session: AsyncSession) -> None:
    async with (
        session.begin(),
        ops.audited(session, STAFF, "ops.user.suspend", TARGET) as audit,
    ):
        audit.before = {"status": "active", "name": "Rafi"}
        audit.after = {"status": "suspended", "name": "Rafi"}
    row = (await session.execute(select(AuditLog))).scalar_one()
    assert (row.action, row.module, row.actor_kind) == ("ops.user.suspend", "ops", "staff")
    assert row.actor_user_id == STAFF.user_id
    assert row.actor_roles == ["ops_admin"]
    assert (row.before, row.after) == ({"status": "active"}, {"status": "suspended"})
    assert row.occurred_on == row.occurred_at.astimezone(UTC).date()
    assert row.ip_hash is None


async def test_failed_block_leaves_no_row(session: AsyncSession) -> None:
    with pytest.raises(LookupError):
        async with session.begin(), ops.audited(session, STAFF, "ops.user.suspend", TARGET):
            raise LookupError("change failed")
    assert await count(session) == 0


async def test_guards(session: AsyncSession) -> None:
    with pytest.raises(RuntimeError, match="transaction"):
        async with ops.audited(session, STAFF, "ops.user.suspend", TARGET):
            pass
    async with session.begin():
        with pytest.raises(ValueError, match=r"module\.thing\.verb"):
            async with ops.audited(session, STAFF, "Bad Action", TARGET):
                pass
        with pytest.raises(ValidationAppError):
            async with ops.audited(session, STAFF, "plan.subscription.refund", TARGET, reason=" "):
                pass
        async with ops.audited(
            session, ops.AuditActor.system(), "plan.subscription.extend", TARGET, reason="outage"
        ):
            pass
    row = (await session.execute(select(AuditLog))).scalar_one()
    assert (row.actor_kind, row.actor_user_id, row.reason) == ("system", None, "outage")


def test_reason_rule() -> None:
    assert needs_reason("auth.grant.grant")
    assert needs_reason("exam.attempt.invalidate")
    assert not needs_reason("ops.runtime_config.update")


def test_redaction_and_diff() -> None:
    before = {"phone": "+8801712345678", "email": None, "otp": "123456", "role": "student"}
    after = {"phone": "+8801812345678", "email": "a@b.com", "otp": "654321", "role": "student"}
    old, new = changed(before, after)
    assert old is not None
    assert new is not None
    assert old["phone"] == {"hash": keyed_hash("+8801712345678", "phone").hex()}
    assert new["email"] == {"hash": keyed_hash("a@b.com", "email").hex()}
    assert old["email"] is None
    assert new["otp"] == "[redacted]"
    assert "role" not in new
    assert "8801812345678" not in str(new)
    nested = redact({"profile": {"guardian_phone": "+8801700000000"}, "at": datetime(2026, 1, 1)})
    assert nested is not None
    assert "hash" in nested["profile"]["guardian_phone"]
    assert nested["at"] == "2026-01-01T00:00:00"
    assert changed(None, {"a": 1}) == (None, {"a": 1})
    assert changed({"x": 1}, {"y": 2}) == ({"x": 1}, {"y": 2})


async def test_audit_log_is_append_only_for_app_rw(session: AsyncSession) -> None:
    async with session.begin(), ops.audited(session, STAFF, "ops.user.suspend", TARGET):
        pass
    with pytest.raises(DBAPIError, match="permission denied"):
        await session.execute(text("UPDATE ops.audit_log SET reason = 'edited'"))


async def test_delete_is_denied(session: AsyncSession) -> None:
    with pytest.raises(DBAPIError, match="permission denied"):
        await session.execute(text("DELETE FROM ops.audit_log"))

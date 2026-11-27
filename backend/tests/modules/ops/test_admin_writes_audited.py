"""Every B1 admin write leaves exactly one audit row naming the staff actor (05 §F.1 item 8).

Each write goes through the real API with a valid body; ``test_audited`` covers the mechanism
(same transaction, rollback leaves no row, append-only grants)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.modules.ops.internal.models import AuditLog
from tests.support.full_app import OTHER_STUDENT, STAFF, STUDENT, staff_header, student_session

pytestmark = [pytest.mark.api, pytest.mark.db]
ADMIN = "/v1/admin"


def idem() -> dict[str, str]:
    return {**staff_header(), "Idempotency-Key": str(uuid.uuid4())}


async def ok(response: httpx.Response, status: int) -> dict[str, object]:
    assert response.status_code == status, response.text
    return {} if status == 204 else dict(response.json())


async def test_each_admin_write_is_audited_once(
    api: httpx.AsyncClient, session: AsyncSession, clock: FrozenClock
) -> None:
    staff = staff_header()
    grant = await ok(await api.post(f"{ADMIN}/role-grants", headers=staff, json={
        "user_id": str(OTHER_STUDENT), "role_code": "teacher", "reason": "matrix test",
    }), 201)  # fmt: skip
    await ok(await api.delete(f"{ADMIN}/role-grants/{grant['id']}", headers=staff), 204)
    await ok(await api.put(f"{ADMIN}/runtime-config/kill.tutor", headers=staff,
                           json={"value": True, "reason": "matrix test"}), 200)  # fmt: skip
    term = await ok(await api.post(f"{ADMIN}/moderation/terms", headers=staff, json={
        "lang": "en", "term": "matrixword", "category": "profanity",
    }), 201)  # fmt: skip
    await ok(await api.delete(f"{ADMIN}/moderation/terms/{term['id']}", headers=staff), 204)
    mute = await ok(await api.post(f"{ADMIN}/moderation/restrictions", headers=idem(), json={
        "user_id": str(OTHER_STUDENT), "kind": "mute", "scope": "profile",
        "reason": "matrix test",
    }), 201)  # fmt: skip
    await ok(await api.delete(f"{ADMIN}/moderation/restrictions/{mute['id']}", headers=staff), 204)
    student, _ = await student_session(session, STUDENT, clock.now())
    report = await ok(await api.post("/v1/reports", headers=student, json={
        "target_type": "user", "target_id": str(OTHER_STUDENT), "reason": "spam",
    }), 201)  # fmt: skip
    resolve = f"{ADMIN}/moderation/reports/{report['report_id']}:resolve"
    body = {"decision": "dismiss", "note": "not abusive"}
    await ok(await api.post(resolve, headers=idem(), json=body), 200)

    async with session.begin():
        rows = (await session.execute(select(AuditLog.action, AuditLog.actor_user_id))).all()
    staff_rows = sorted(action for action, actor in rows if actor == STAFF)
    assert staff_rows == sorted([
        "auth.role.grant", "auth.role.revoke", "ops.runtime_config.update", "com.term.create",
        "com.term.delete", "com.restriction.mute", "com.restriction.lift", "com.report.resolve",
    ])  # fmt: skip

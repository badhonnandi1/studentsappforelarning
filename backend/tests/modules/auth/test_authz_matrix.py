"""Every B1 route against {anonymous, student, other student, staff without permission, staff with
permission} (05 §E). The table must name every route, so a new route fails here until it is
classified. "Allowed" means the auth gate let the call through: any status but 401 and 403
(a 422 for an empty body proves the gate passed, since auth dependencies run first)."""

from __future__ import annotations

import uuid
from typing import Literal

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from scripts.export_openapi import document
from tests.support.full_app import (
    OTHER_STUDENT,
    STAFF_NO_GRANT,
    STUDENT,
    staff_header,
    student_session,
)

pytestmark = [pytest.mark.api, pytest.mark.db]
Kind = Literal["public", "user", "owned", "staff"]
P: Kind = "public"
U: Kind = "user"
OWN: Kind = "owned"
S: Kind = "staff"
ROUTES: dict[str, Kind] = {
    "GET /livez": P, "GET /readyz": P,
    "POST /v1/auth/otp/send": P, "POST /v1/auth/otp/verify": P, "POST /v1/auth/refresh": P,
    "POST /v1/auth/sign-up/complete": P, "POST /v1/auth/social/nonce": P,
    "POST /v1/auth/social/{provider}": P, "GET /v1/auth/social/facebook/deletion-status/{code}": P,
    "POST /v1/webhooks/facebook/data-deletion": P, "POST /v1/webhooks/facebook/deauthorize": P,
    "GET /v1/admin/auth/sso/start": P, "GET /v1/admin/auth/sso/callback": P,
    "GET /v1/config/client": P, "GET /v1/consent-documents/{version}": P,
    "GET /v1/reference/districts": P, "GET /v1/reference/institutions": P,
    "POST /v1/auth/logout": U, "POST /v1/auth/step-up": U, "POST /v1/auth/step-up/send": U,
    "GET /v1/me": U, "PATCH /v1/me": U, "POST /v1/me/phone": U,
    "GET /v1/me/profile": U, "PUT /v1/me/profile": U, "POST /v1/me/profile/photo": U,
    "GET /v1/me/privacy": U, "PUT /v1/me/privacy": U,
    "POST /v1/me/consent/guardian/start": U, "POST /v1/me/consent/guardian/confirm": U,
    "GET /v1/me/identities": U, "POST /v1/me/identities/{provider}": U,
    "DELETE /v1/me/identities/{provider}": U, "GET /v1/me/sessions": U,
    "DELETE /v1/me/sessions/{session_id}": OWN,
    "POST /v1/reports": U, "GET /v1/uploads/{purpose}/presign": U,
    "GET /v1/admin/audit-log": S, "PUT /v1/admin/runtime-config/{key}": S,
    "POST /v1/admin/role-grants": S, "DELETE /v1/admin/role-grants/{grant_id}": S,
    "GET /v1/admin/moderation/reports": S,
    "POST /v1/admin/moderation/reports/{report_id}:resolve": S,
    "POST /v1/admin/moderation/restrictions": S,
    "DELETE /v1/admin/moderation/restrictions/{restriction_id}": S,
    "GET /v1/admin/moderation/terms": S, "POST /v1/admin/moderation/terms": S,
    "DELETE /v1/admin/moderation/terms/{term_id}": S,
}  # fmt: skip
PARAMS = {"provider": "google", "code": "abc123", "version": "2026-11-v1", "key": "kill.tutor",
          "purpose": "profile_photo", "grant_id": str(uuid.uuid4()),
          "report_id": str(uuid.uuid4()), "restriction_id": str(uuid.uuid4()),
          "term_id": str(uuid.uuid4())}  # fmt: skip
# A 403 with one of these codes comes from a check after the auth gate, so the gate passed.
AFTER_GATE = frozenset({"step_up_required", "phone_required"})


def denied(response: httpx.Response) -> bool:
    if response.status_code == 401:
        return True
    if response.status_code != 403:
        return False
    return response.json()["error"]["code"] not in AFTER_GATE


def test_every_route_is_classified() -> None:
    served = {f"{m.upper()} {path}" for path, ops in document()["paths"].items() for m in ops}
    assert served == set(ROUTES)


async def call(
    api: httpx.AsyncClient, route: str, headers: dict[str, str], **params: str
) -> httpx.Response:
    method, template = route.split(" ", 1)
    path = template.format(**{**PARAMS, **params})
    body: dict[str, str] | None = None if method in ("GET", "DELETE") else {}
    return await api.request(method, path, json=body, headers=headers)


@pytest.mark.parametrize("route", sorted(ROUTES))
async def test_route_matrix(
    api: httpx.AsyncClient, session: AsyncSession, clock: FrozenClock, route: str
) -> None:
    kind, now = ROUTES[route], clock.now()
    own, own_sid = await student_session(session, STUDENT, now)
    other, _ = await student_session(session, OTHER_STUDENT, now)
    sid = {"session_id": str(own_sid)}
    cells = {
        "anonymous": await call(api, route, {}, **sid),
        "other student": await call(api, route, other, **sid),
        "staff without permission": await call(api, route, staff_header(STAFF_NO_GRANT), **sid),
        "staff": await call(api, route, staff_header(), **sid),
        "student": await call(api, route, own, **sid),  # last: it may end its own session
    }
    status = {cell: r.status_code for cell, r in cells.items()}
    gate = {cell: not denied(r) for cell, r in cells.items()}
    if kind == "public":
        assert all(gate.values()), status
    elif kind == "staff":
        assert gate["staff"], status
        assert status["staff without permission"] == 403, status
        for cell in ("anonymous", "student", "other student"):
            assert status[cell] == 401, status  # an app token is not an admin token
    else:
        assert status["anonymous"] == 401, status
        assert gate["student"], status
        assert gate["other student"], status
        assert status["staff"] == status["staff without permission"] == 401, status
        if kind == "owned":
            assert status["other student"] == 404, status  # another student's session

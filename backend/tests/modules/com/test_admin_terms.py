"""``/v1/admin/moderation/terms``: add (folded), duplicate, list, soft delete, audit, access."""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import com
from app.modules.ops.internal.models import AuditLog
from tests.modules.com.conftest import OUTSIDER, as_staff

pytestmark = [pytest.mark.api, pytest.mark.db, pytest.mark.usefixtures("staff")]
URL = "/v1/admin/moderation/terms"


async def add(client: httpx.AsyncClient, term: str, **body: str) -> httpx.Response:
    payload = {"lang": "banglish", "term": term, "category": "profanity", **body}
    return await client.post(URL, json=payload, headers=as_staff())


async def actions(session: AsyncSession) -> list[str]:
    rows = (await session.execute(select(AuditLog.action).order_by(AuditLog.occurred_at))).all()
    await session.commit()
    return [r[0] for r in rows]


async def test_add_folds_and_takes_effect(client: httpx.AsyncClient, session: AsyncSession) -> None:
    assert (await com.moderate(session, "Shoytan!", "post")).verdict == "allow"
    created = await add(client, "SHOYTAAN", severity="high")
    assert created.status_code == 201, created.text
    assert created.json()["term_folded"] == "soitan"
    assert created.json()["severity"] == "high"
    assert (await com.moderate(session, "Shoytan!", "post")).verdict == "block"
    assert (await add(client, "shoitan")).status_code == 409
    assert await actions(session) == ["com.term.create"]


async def test_empty_after_folding_is_422(client: httpx.AsyncClient) -> None:
    response = await add(client, "!!!")
    assert response.status_code == 422
    assert response.json()["error"]["details"] == {"term": "empty"}


async def test_list_pages_and_filters(client: httpx.AsyncClient, session: AsyncSession) -> None:
    for term in ("alpha", "bravo", "charlie"):
        assert (await add(client, term)).status_code == 201
    assert (await add(client, "delta", lang="en")).status_code == 201
    first = await client.get(URL, params={"limit": 2, "lang": "banglish"}, headers=as_staff())
    assert first.status_code == 200
    body = first.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]
    params = {"limit": 2, "lang": "banglish", "cursor": body["next_cursor"]}
    rest = (await client.get(URL, params=params, headers=as_staff())).json()
    assert len(rest["items"]) == 1
    assert rest["next_cursor"] is None
    everything = (await client.get(URL, headers=as_staff())).json()["items"]
    assert len(everything) == 4
    bad = await client.get(URL, params={"cursor": "not-a-cursor"}, headers=as_staff())
    assert bad.status_code == 422


async def test_delete_is_soft_and_term_can_return(
    client: httpx.AsyncClient, session: AsyncSession
) -> None:
    term_id = (await add(client, "shoytan")).json()["id"]
    deleted = await client.delete(f"{URL}/{term_id}", headers=as_staff())
    assert deleted.status_code == 204
    assert (await com.moderate(session, "shoytan", "post")).verdict == "allow"
    assert (await client.delete(f"{URL}/{term_id}", headers=as_staff())).status_code == 404
    assert (await client.delete(f"{URL}/{uuid.uuid4()}", headers=as_staff())).status_code == 404
    again = await add(client, "shoytan", severity="low")
    assert again.status_code == 201
    assert again.json()["id"] == term_id
    assert (await com.moderate(session, "shoytan", "post")).verdict == "flag"
    assert await actions(session) == ["com.term.create", "com.term.delete", "com.term.create"]


async def test_needs_moderation_permission(client: httpx.AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401
    assert (await client.get(URL, headers=as_staff(OUTSIDER))).status_code == 403

"""No plain-text phone or email anywhere at rest (05 §F.1 item 9, 14 §1.9).

Each test runs in a rolled-back transaction, so "after the suite" the database is empty.
Instead, this test drives every B1 flow that handles a phone, guardian phone or email through
the API, then scans every text, JSON and bytea column of every module schema, and every Redis
key and value. Phones are searched for in all common spellings.
"""

from __future__ import annotations

import re

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.registry import SCHEMAS
from tests.modules.auth.conftest import TEST_CODE, auth_header, sign_up
from tests.modules.auth.test_social import social
from tests.modules.auth.test_step_up import step_up

pytestmark = [pytest.mark.api, pytest.mark.db, pytest.mark.usefixtures("fakes")]
MINOR, GUARDIAN, NEW = "+8801700000011", "+8801700000012", "+8801700000013"
EMAIL = "kid@example.com"  # the fake Google identity's verified email
NEEDLES = (MINOR[4:], GUARDIAN[4:], NEW[4:], EMAIL)  # "1700000011" matches +880, 880 and 0 forms
PHONE_RE = r"(\+?880|(^|[^0-9])0)1[3-9][0-9]{8}($|[^0-9])"
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+"
TEXT_TYPES = ("text", "character varying", "json", "jsonb", "ARRAY")


async def drive_pii_flows(client: httpx.AsyncClient) -> None:
    minor = auth_header(await sign_up(client, MINOR, dob="2012-02-02"))
    consent = {"guardian_phone": GUARDIAN, "guardian_relation": "mother",
               "consent_version": "2026-11-v1"}  # fmt: skip
    started = await client.post("/v1/me/consent/guardian/start", json=consent, headers=minor)
    confirm = {"challenge_id": started.json()["challenge_id"], "code": TEST_CODE}
    granted = await client.post("/v1/me/consent/guardian/confirm", json=confirm, headers=minor)
    assert granted.status_code == 200, granted.text

    stepped = {**minor, "X-Step-Up-Token": await step_up(client, minor, "phone_change")}
    change = await client.post("/v1/me/phone", json={"phone": NEW}, headers=stepped)
    assert change.status_code == 202, change.text
    body = {"challenge_id": change.json()["challenge_id"], "code": TEST_CODE}
    assert (await client.post("/v1/me/phone", json=body, headers=minor)).status_code == 200

    pending = (await social(client, "google")).json()
    body = {"pending_signup_token": pending["pending_signup_token"], "date_of_birth": "2001-01-01"}
    assert (await client.post("/v1/auth/sign-up/complete", json=body)).status_code == 201
    assert (await social(client, "google")).status_code == 200  # sign in again


async def columns(session: AsyncSession) -> list[tuple[str, str, str, str]]:
    rows = await session.execute(
        text(
            "SELECT c.table_schema, c.table_name, c.column_name, c.data_type"
            " FROM information_schema.columns c JOIN information_schema.tables t"
            " USING (table_schema, table_name)"
            " WHERE c.table_schema = ANY(:schemas) AND t.table_type = 'BASE TABLE'"
        ),
        {"schemas": list(SCHEMAS)},
    )
    return [(r[0], r[1], r[2], r[3]) for r in rows]


async def hits_in_database(session: AsyncSession) -> list[str]:
    found = []
    for schema, table, column, kind in await columns(session):
        ref, col = f'"{schema}"."{table}"', f'"{column}"'
        if kind == "bytea":
            where = " OR ".join(
                f"position(convert_to(:n{i}, 'UTF8') in {col}) > 0" for i in range(len(NEEDLES))
            )
        elif kind in TEXT_TYPES:
            where = f"{col}::text ~ :phone OR {col}::text ~ :email"
        else:
            continue
        params = {f"n{i}": n for i, n in enumerate(NEEDLES)} | {
            "phone": PHONE_RE,
            "email": EMAIL_RE,
        }
        sql = text(f"SELECT count(*) FROM {ref} WHERE {where}")  # noqa: S608 - catalogue names
        if (await session.execute(sql, params)).scalar_one():
            found.append(f"{schema}.{table}.{column}")
    return found


async def hits_in_redis(redis: Redis) -> list[str]:
    pattern = re.compile(f"{PHONE_RE}|{EMAIL_RE}|" + "|".join(map(re.escape, NEEDLES)))
    found = []
    async for key in redis.scan_iter(count=500):
        raw_kind = await redis.type(key)
        kind = raw_kind.decode() if isinstance(raw_kind, bytes) else str(raw_kind)
        if kind == "string":
            values = [await redis.get(key)]
        elif kind == "hash":
            values = [*(await redis.hgetall(key)).values()]
        else:
            values = []
        for blob in (key, *values):
            if isinstance(blob, bytes) and pattern.search(blob.decode(errors="replace")):
                found.append(f"{kind} {key.decode(errors='replace')}")
                break
    return found


async def test_no_plaintext_phone_or_email_at_rest(
    client: httpx.AsyncClient, session: AsyncSession, app_redis: Redis
) -> None:
    await drive_pii_flows(client)
    assert await hits_in_database(session) == []
    assert await hits_in_redis(app_redis) == []
    # the scan itself works: plant one plain value in each store and it is the only hit
    await session.execute(text("UPDATE identity.users SET display_name = '01700000011'"))
    await app_redis.set("planted", EMAIL)
    assert await hits_in_database(session) == ["identity.users.display_name"]
    assert await hits_in_redis(app_redis) == ["string planted"]

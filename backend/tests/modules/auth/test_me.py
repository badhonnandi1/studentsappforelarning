"""``/v1/me`` and ``/v1/me/sessions`` (05 §D)."""

from __future__ import annotations

import uuid

import httpx
import pytest

from tests.modules.auth.conftest import auth_header, sign_in, sign_up

pytestmark = [pytest.mark.api, pytest.mark.db]


async def test_get_me(client: httpx.AsyncClient) -> None:
    pair = await sign_up(client, dob="2010-03-04")
    me = await client.get("/v1/me", headers=auth_header(pair))
    assert me.status_code == 200
    body = me.json()
    assert body["phone_masked"] == "01*******01"
    assert body["identities"] == []
    assert body["consent"] == {"required": True, "status": "missing"}
    assert body["roles"] == ["student"]
    adult = await sign_up(client, "+8801700000002", device_id="device-0002")
    other = (await client.get("/v1/me", headers=auth_header(adult))).json()
    assert other["consent"] == {"required": False, "status": "not_required"}


async def test_patch_me(client: httpx.AsyncClient) -> None:
    pair = await sign_up(client)
    body = {"display_name": "Rahim Uddin", "first_name": "রহিম", "locale": "en"}
    patched = await client.patch("/v1/me", json=body, headers=auth_header(pair))
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Rahim Uddin"
    assert patched.json()["first_name"] == "রহিম"
    for bad in ({"display_name": "x"}, {"display_name": "bad<script>"}, {"locale": "fr"}):
        response = await client.patch("/v1/me", json=bad, headers=auth_header(pair))
        assert response.status_code == 422, bad
    assert (await client.get("/v1/me")).status_code == 401


async def test_sessions_list_and_revoke(client: httpx.AsyncClient) -> None:
    phone_a = await sign_up(client, device_id="device-aaaa", model="Pixel 8")
    phone_b = await sign_in(client, device_id="device-bbbb")
    listed = await client.get("/v1/me/sessions", headers=auth_header(phone_a))
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 2
    current = [i for i in items if i["current"]]
    assert [i["session_id"] for i in current] == [phone_a["session_id"]]
    assert current[0]["model"] == "Pixel 8"
    url = f"/v1/me/sessions/{phone_b['session_id']}"
    assert (await client.delete(url, headers=auth_header(phone_a))).status_code == 204
    assert (await client.get("/v1/me", headers=auth_header(phone_b))).status_code == 401
    assert (await client.delete(url, headers=auth_header(phone_a))).status_code == 404
    unknown = f"/v1/me/sessions/{uuid.uuid4()}"
    assert (await client.delete(unknown, headers=auth_header(phone_a))).status_code == 404

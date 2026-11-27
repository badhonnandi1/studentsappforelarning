"""``/v1/me/profile``, the photo and the reference lists (05 §D, §C.4)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import District, Institution, Upazila
from tests.modules.auth.conftest import UPLOADS, auth_header, sign_up, uploads_storage
from tests.shared.test_image_header import jpeg, png

pytestmark = [pytest.mark.api, pytest.mark.db]
SCHOOL = uuid.UUID("00000000-0000-7000-8000-0000000005c1")
CLOSED = uuid.UUID("00000000-0000-7000-8000-0000000005c2")


@pytest.fixture
async def places(sessions: Callable[[], AsyncSession]) -> None:
    async with sessions() as s, s.begin():
        s.add_all([
            District(id=1, division="Dhaka", name_bn="ঢাকা", name_en="Dhaka"),
            District(id=2, division="Chattogram", name_bn="চট্টগ্রাম", name_en="Chattogram"),
        ])  # fmt: skip
        await s.flush()
        s.add_all([
            Upazila(id=101, district_id=1, name_bn="সাভার", name_en="Savar"),
            Upazila(id=201, district_id=2, name_bn="হাটহাজারী", name_en="Hathazari"),
            Institution(id=SCHOOL, name_bn="ঢাকা রেসিডেনসিয়াল মডেল কলেজ",
                        name_en="Dhaka Residential Model College", kind="school_college",
                        district_id=1),
            Institution(id=CLOSED, name_bn="বন্ধ স্কুল", name_en="Dhaka Closed School",
                        kind="school", district_id=1, is_active=False),
        ])  # fmt: skip


def profile(**changes: Any) -> dict[str, Any]:
    body = {"class_level": 10, "group_code": "science", "version_lang": "bn",
            "curriculum": "general", "district_id": 1, "upazila_id": 101,
            "institution_id": str(SCHOOL), "exam_year": 2027}  # fmt: skip
    body.update(changes)
    return {k: v for k, v in body.items() if v is not None}


@pytest.mark.usefixtures("places")
async def test_put_and_get_profile(client: httpx.AsyncClient) -> None:
    headers = auth_header(await sign_up(client, dob="2011-04-04"))
    empty = (await client.get("/v1/me/profile", headers=headers)).json()
    assert empty["class_level"] is None
    assert empty["needs_consent"] is True
    saved = await client.put("/v1/me/profile", json=profile(), headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["group_code"] == "science"
    job = profile(class_level="job", group_code=None, exam_year=None, date_of_birth="2011-04-04")
    again = await client.put("/v1/me/profile", json=job, headers=headers)
    assert again.json()["class_level"] == "job"
    assert (await client.get("/v1/me/profile", headers=headers)).json()["class_level"] == "job"


@pytest.mark.usefixtures("places")
@pytest.mark.parametrize(
    ("changes", "status", "field"),
    [
        ({"group_code": None}, 422, "group_code"),
        ({"class_level": 7}, 422, "group_code"),
        ({"class_level": 13}, 422, None),
        ({"exam_year": 2020}, 422, "exam_year"),
        ({"exam_year": 2040}, 422, "exam_year"),
        ({"district_id": 9}, 422, "district_id"),
        ({"upazila_id": 201}, 422, "upazila_id"),
        ({"institution_id": str(CLOSED)}, 404, "institution_id"),
        ({"institution_id": str(uuid.uuid4())}, 404, "institution_id"),
        ({"date_of_birth": "2010-01-01"}, 422, "date_of_birth"),
        ({"curriculum": "online"}, 422, None),
    ],
)
async def test_profile_rules(
    client: httpx.AsyncClient, changes: dict[str, Any], status: int, field: str | None
) -> None:
    headers = auth_header(await sign_up(client, dob="2011-04-04"))
    response = await client.put("/v1/me/profile", json=profile(**changes), headers=headers)
    assert response.status_code == status, response.text
    if field is not None:
        assert response.json()["error"]["details"]["field"] == field


@pytest.mark.usefixtures("places")
async def test_reference_lists(client: httpx.AsyncClient) -> None:
    districts = await client.get("/v1/reference/districts")
    assert districts.status_code == 200
    assert districts.headers["Cache-Control"] == "public, max-age=86400"
    first = districts.json()["items"][0]
    assert first["name_en"] == "Dhaka"
    assert [u["name_en"] for u in first["upazilas"]] == ["Savar"]
    found = await client.get("/v1/reference/institutions", params={"q": "residential"})
    assert [i["id"] for i in found.json()["items"]] == [str(SCHOOL)]
    assert found.json()["next_cursor"] is None
    fuzzy = await client.get("/v1/reference/institutions", params={"q": "Dhaka Residentail"})
    assert [i["id"] for i in fuzzy.json()["items"]] == [str(SCHOOL)]
    bangla = await client.get("/v1/reference/institutions", params={"q": "রেসিডেনসিয়াল"})
    assert len(bangla.json()["items"]) == 1
    by_district = await client.get("/v1/reference/institutions", params={"district_id": 2})
    assert by_district.json()["items"] == []
    listed = await client.get("/v1/reference/institutions", params={"district_id": 1})
    assert len(listed.json()["items"]) == 1  # the inactive one is hidden
    assert (await client.get("/v1/reference/institutions")).status_code == 422
    assert (await client.get("/v1/reference/institutions", params={"q": "d"})).status_code == 422


async def upload(client: httpx.AsyncClient, pair: dict[str, Any], body: bytes, ext: str) -> str:
    store = uploads_storage()
    await store.ensure_bucket(UPLOADS)
    key = f"profile_photo/2026/11/{pair['user']['id']}/{uuid.uuid4()}.{ext}"
    kind = "image/png" if ext == "png" else "image/jpeg"
    await store.put_object(UPLOADS, key, body, kind)
    return key


@pytest.mark.integration
async def test_photo_checks(client: httpx.AsyncClient) -> None:
    pair = await sign_up(client)
    headers = auth_header(pair)
    url = "/v1/me/profile/photo"
    good = await upload(client, pair, png(256, 256), "png")
    accepted = await client.post(url, json={"upload_key": good}, headers=headers)
    assert accepted.status_code == 202
    assert accepted.json() == {"photo_status": "pending"}
    assert (await client.get("/v1/me/profile", headers=headers)).json()["photo_status"] == "pending"
    cases = [
        await upload(client, pair, png(32, 32), "png"),  # too small
        await upload(client, pair, jpeg(300, 300), "png"),  # type does not match the key
        await upload(client, pair, b"not an image at all", "jpg"),
        f"profile_photo/2026/11/{pair['user']['id']}/{uuid.uuid4()}.png",  # never uploaded
        f"profile_photo/2026/11/{uuid.uuid4()}/{uuid.uuid4()}.png",  # someone else's
        "../../etc/passwd/xxxxxxxx",
    ]
    for key in cases:
        refused = await client.post(url, json={"upload_key": key}, headers=headers)
        assert refused.status_code == 422, key
        assert refused.json()["error"]["code"] == "invalid_upload"

import uuid
from datetime import UTC, datetime

import httpx
import pytest

from app.core.errors import ValidationAppError
from app.core.settings import Settings
from app.core.storage import Storage, object_key

pytestmark = pytest.mark.integration
NOW = datetime(2026, 5, 1, tzinfo=UTC)


@pytest.fixture
async def storage() -> Storage:
    settings = Settings(_env_file=None, s3_bucket_uploads="sp-test-uploads")
    store = Storage(settings)
    await store.ensure_bucket("sp-test-uploads")
    await store.ensure_bucket("sp-test-uploads")  # idempotent
    return store


def test_object_key_is_owner_scoped() -> None:
    owner = uuid.uuid4()
    key = object_key("profile_photo", owner, "jpg", NOW)
    assert key.startswith(f"profile_photo/2026/05/{owner}/")
    assert key.endswith(".jpg")


async def test_presigned_upload_enforces_size_and_type(storage: Storage) -> None:
    owner = uuid.uuid4()
    upload = await storage.presign_upload("profile_photo", owner, "image/png", NOW)
    assert upload.max_bytes == 2 * 1024 * 1024
    async with httpx.AsyncClient() as client:
        files = {"file": ("a.png", b"\x89PNG....", "image/png")}
        ok = await client.post(upload.url, data=upload.fields, files=files)
        assert ok.status_code == 204
        wrong_type = {**upload.fields, "Content-Type": "text/html"}
        bad = await client.post(upload.url, data=wrong_type, files=files)
        assert bad.status_code == 403
    assert await storage.get_object("sp-test-uploads", upload.key) == b"\x89PNG...."
    url = await storage.presign_get("sp-test-uploads", upload.key)
    async with httpx.AsyncClient() as client:
        assert (await client.get(url)).content == b"\x89PNG...."


async def test_presign_rejects_unknown_purpose_or_type(storage: Storage) -> None:
    with pytest.raises(ValidationAppError):
        await storage.presign_upload("nope", uuid.uuid4(), "image/png", NOW)
    with pytest.raises(ValidationAppError):
        await storage.presign_upload("profile_photo", uuid.uuid4(), "application/pdf", NOW)


async def test_put_and_list(storage: Storage) -> None:
    prefix = f"t/{uuid.uuid4()}/"
    await storage.put_object("sp-test-uploads", prefix + "a.txt", b"hi", "text/plain")
    assert await storage.list_keys("sp-test-uploads", prefix) == [prefix + "a.txt"]

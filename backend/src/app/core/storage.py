"""S3 access (aioboto3): presigned uploads with size and type limits, presigned downloads.

Files never pass through the API (14 §1.3). Uploads use a presigned POST because only a POST
policy can enforce ``content-length-range``; a presigned PUT cannot cap the size.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aioboto3

from app.core.errors import ValidationAppError
from app.core.ids import uuid7
from app.core.settings import Settings

PRESIGN_TTL_S = 600
MiB = 1024 * 1024


@dataclass(frozen=True)
class UploadPurpose:
    name: str
    content_types: dict[str, str]  # content type -> file extension
    max_bytes: int


IMAGES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
JPEG_PNG = {"image/jpeg": "jpg", "image/png": "png"}
PURPOSES: dict[str, UploadPurpose] = {
    p.name: p
    for p in (
        UploadPurpose("profile_photo", JPEG_PNG, 2 * MiB),
        UploadPurpose("photo_solve", IMAGES, 8 * MiB),
        UploadPurpose("submission_page", IMAGES, 10 * MiB),
        UploadPurpose(
            "import_file",
            {
                "text/csv": "csv",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
            },
            20 * MiB,
        ),
    )
}


@dataclass(frozen=True)
class PresignedUpload:
    url: str
    fields: dict[str, str]
    key: str
    expires_in: int
    max_bytes: int


def object_key(purpose: str, owner_id: uuid.UUID, ext: str, now: datetime) -> str:
    """``<purpose>/<yyyy>/<mm>/<owner>/<uuid7>.<ext>``: owner-scoped, unguessable, sortable."""
    return f"{purpose}/{now:%Y}/{now:%m}/{owner_id}/{uuid7()}.{ext}"


class Storage:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.session = aioboto3.Session()

    def _client(self) -> Any:
        return self.session.client(
            "s3", endpoint_url=self.settings.s3_endpoint_url, region_name=self.settings.aws_region
        )

    async def presign_upload(
        self, purpose: str, owner_id: uuid.UUID, content_type: str, now: datetime
    ) -> PresignedUpload:
        spec = PURPOSES.get(purpose)
        if spec is None:
            raise ValidationAppError("Unknown upload purpose", code="validation_error")
        ext = spec.content_types.get(content_type)
        if ext is None:
            raise ValidationAppError("Content type not allowed for this purpose")
        key = object_key(purpose, owner_id, ext, now)
        async with self._client() as s3:
            post = await s3.generate_presigned_post(
                Bucket=self.settings.s3_bucket_uploads,
                Key=key,
                Fields={"Content-Type": content_type},
                Conditions=[
                    {"Content-Type": content_type},
                    ["content-length-range", 1, spec.max_bytes],
                ],
                ExpiresIn=PRESIGN_TTL_S,
            )
        return PresignedUpload(
            post["url"], dict(post["fields"]), key, PRESIGN_TTL_S, spec.max_bytes
        )

    async def presign_get(self, bucket: str, key: str, expires_in: int = PRESIGN_TTL_S) -> str:
        async with self._client() as s3:
            url: str = await s3.generate_presigned_url(
                "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in
            )
        return url

    async def put_object(self, bucket: str, key: str, body: bytes, content_type: str) -> None:
        async with self._client() as s3:
            await s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)

    async def get_object(self, bucket: str, key: str) -> bytes:
        async with self._client() as s3:
            response = await s3.get_object(Bucket=bucket, Key=key)
            async with response["Body"] as stream:
                data: bytes = await stream.read()
        return data

    async def list_keys(self, bucket: str, prefix: str) -> list[str]:
        async with self._client() as s3:
            response = await s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
        return [item["Key"] for item in response.get("Contents", [])]

    async def ensure_bucket(self, bucket: str) -> None:
        """Local and test only: buckets are created by infrastructure in deployed envs."""
        async with self._client() as s3:
            existing = await s3.list_buckets()
            if bucket not in {b["Name"] for b in existing.get("Buckets", [])}:
                await s3.create_bucket(
                    Bucket=bucket,
                    CreateBucketConfiguration={"LocationConstraint": self.settings.aws_region},
                )

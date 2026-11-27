"""``GET /v1/uploads/{purpose}/presign``: a presigned S3 POST for a direct upload (05 §D).

Files never pass through the API (R-32). The POST policy caps the size and pins the type.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.clock import Clock, get_clock
from app.core.errors import ValidationAppError
from app.core.security.actor import Actor
from app.core.security.deps import user_tier
from app.core.storage import PURPOSES, Storage, get_storage
from app.modules.nfr.internal.schemas.config import PresignOut

router = APIRouter(prefix="/v1/uploads", tags=["uploads"])
ENABLED = frozenset({"profile_photo"})  # later builds add theirs


@router.get("/{purpose}/presign", response_model=PresignOut)
async def presign(
    purpose: str,
    content_type: Annotated[str, Query(max_length=100)],
    size: Annotated[int, Query(alias="bytes", ge=1)],
    actor: Annotated[Actor, Depends(user_tier("upload"))],
    storage: Annotated[Storage, Depends(get_storage)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> PresignOut:
    spec = PURPOSES.get(purpose)
    if spec is None or purpose not in ENABLED:
        raise ValidationAppError("Unknown upload purpose", details={"field": "purpose"})
    if size > spec.max_bytes:
        raise ValidationAppError("The file is too large", details={"max_bytes": spec.max_bytes})
    now = clock.now()
    signed = await storage.presign_upload(purpose, actor.user_id, content_type, now)
    return PresignOut(
        upload_url=signed.url,
        fields=signed.fields,
        key=signed.key,
        expires_at=now + timedelta(seconds=signed.expires_in),
        max_bytes=signed.max_bytes,
    )

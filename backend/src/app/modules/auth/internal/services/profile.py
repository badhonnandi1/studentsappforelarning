"""``/v1/me/profile`` and the profile photo (05 §D, rules in §C.4).

Display-name moderation and photo moderation by a provider arrive with COM (step 11) and B4;
in B1 a photo gets format, size and dimension checks and stays ``pending`` (not public).
"""

from __future__ import annotations

import re
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.core.security.actor import Actor
from app.core.storage import PURPOSES, Storage
from app.modules.auth.internal.models import Profile, User
from app.modules.auth.internal.repositories import profiles as repo
from app.modules.auth.internal.schemas.profile import (
    CLASS_WORDS,
    PhotoIn,
    PhotoOut,
    ProfileIn,
    ProfileOut,
)
from app.modules.auth.internal.services import summary
from app.shared.dhaka_date import dhaka_today
from app.shared.image_header import image_info

BOARD_CLASSES = range(9, 13)  # classes 9–12 choose a group
BOARD_GROUPS = frozenset({"science", "business", "humanities"})
EXAM_YEARS_AHEAD = 6
PHOTO = PURPOSES["profile_photo"]
PHOTO_MIN_PX, PHOTO_MAX_PX = 64, 4096
WORDS_BY_LEVEL = {v: k for k, v in CLASS_WORDS.items()}


def invalid(field: str, message: str, code: str = "validation_error") -> ValidationAppError:
    return ValidationAppError(message, code=code, details={"field": field})


PROFILE_FIELDS = (
    "group_code", "version_lang", "curriculum", "institution_id", "district_id", "upazila_id",
    "board_code", "exam_year",
)  # fmt: skip


def _out(profile: Profile | None, user: User, needs_consent: bool) -> ProfileOut:
    values: dict[str, object] = dict.fromkeys(PROFILE_FIELDS)
    values.update(class_level=None, photo_status="none")
    if profile is not None:
        values.update({f: getattr(profile, f) for f in PROFILE_FIELDS})
        level = profile.class_level
        values["class_level"] = WORDS_BY_LEVEL.get(level, level) if level is not None else None
        values["photo_status"] = profile.photo_status
    values.update(date_of_birth=user.date_of_birth, needs_consent=needs_consent)
    return ProfileOut.model_validate(values)


async def get_profile(session: AsyncSession, actor: Actor, now: datetime) -> ProfileOut:
    user = await summary.signed_in_user(session, actor)
    profile = await repo.get(session, user.id)
    out = _out(profile, user, await summary.needs_consent(session, user, now))
    await session.commit()  # end the read-only transaction
    return out


async def _validate(session: AsyncSession, body: ProfileIn, now: datetime) -> int:
    level = CLASS_WORDS[body.class_level] if isinstance(body.class_level, str) else body.class_level
    if level in BOARD_CLASSES and body.group_code not in BOARD_GROUPS:
        raise invalid("group_code", "Choose science, business or humanities for classes 9–12")
    if level not in BOARD_CLASSES and body.group_code not in (None, "general"):
        raise invalid("group_code", "A group applies only to classes 9–12")
    year = dhaka_today(now).year
    if body.exam_year is not None and not year <= body.exam_year <= year + EXAM_YEARS_AHEAD:
        raise invalid(
            "exam_year", f"Exam year must be between {year} and {year + EXAM_YEARS_AHEAD}"
        )
    if body.institution_id and await repo.active_institution(session, body.institution_id) is None:
        raise NotFoundError("Institution not found", details={"field": "institution_id"})
    if body.district_id is not None and not await repo.district_exists(session, body.district_id):
        raise invalid("district_id", "Unknown district")
    if body.upazila_id is not None:
        district = await repo.upazila_district(session, body.upazila_id)
        if district is None or district != body.district_id:
            raise invalid("upazila_id", "The upazila must belong to the chosen district")
    return level


async def put_profile(
    session: AsyncSession, actor: Actor, body: ProfileIn, now: datetime
) -> ProfileOut:
    async with session.begin():
        user = await summary.signed_in_user(session, actor, lock=True)
        level = await _validate(session, body, now)
        if body.date_of_birth is not None and body.date_of_birth != user.date_of_birth:
            raise invalid("date_of_birth", "Contact support to change your date of birth",
                          code="dob_locked")  # fmt: skip
        profile = await repo.get_or_new(session, user.id)
        profile.class_level, profile.group_code = level, body.group_code
        profile.version_lang, profile.curriculum = body.version_lang, body.curriculum
        profile.institution_id, profile.district_id = body.institution_id, body.district_id
        profile.upazila_id, profile.board_code = body.upazila_id, body.board_code
        profile.exam_year = body.exam_year
        await session.flush()
        return _out(profile, user, await summary.needs_consent(session, user, now))


def _photo_key_pattern(actor: Actor) -> re.Pattern[str]:
    exts = "|".join(PHOTO.content_types.values())
    return re.compile(rf"^profile_photo/\d{{4}}/\d{{2}}/{actor.user_id}/[0-9a-f-]{{36}}\.({exts})$")


async def check_photo(storage: Storage, bucket: str, key: str) -> None:
    """Format, size and dimensions; anything else is ``422 invalid_upload``."""
    bad = ValidationAppError("The uploaded photo is not usable", code="invalid_upload")
    try:
        data = await storage.get_object(bucket, key)
    except (ClientError, BotoCoreError) as exc:
        raise bad from exc
    info = image_info(data)
    if info is None or len(data) > PHOTO.max_bytes:
        raise bad
    if PHOTO.content_types.get(info.content_type) != key.rsplit(".", 1)[1]:
        raise bad
    if not all(PHOTO_MIN_PX <= px <= PHOTO_MAX_PX for px in (info.width, info.height)):
        raise bad


async def set_photo(
    session: AsyncSession, actor: Actor, body: PhotoIn, storage: Storage
) -> PhotoOut:
    if not _photo_key_pattern(actor).match(body.upload_key):
        raise ValidationAppError("The upload key is not yours", code="invalid_upload")
    await check_photo(storage, storage.settings.s3_bucket_uploads, body.upload_key)
    async with session.begin():
        user = await summary.signed_in_user(session, actor)
        profile = await repo.get_or_new(session, user.id)
        profile.photo_key, profile.photo_status = body.upload_key, "pending"
    return PhotoOut()

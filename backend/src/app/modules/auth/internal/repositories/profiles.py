"""Profiles and the district, upazila and institution reference lists."""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import District, Institution, Profile, Upazila


async def get(session: AsyncSession, user_id: uuid.UUID, *, lock: bool = False) -> Profile | None:
    return await session.get(Profile, user_id, with_for_update=lock, populate_existing=lock)


async def get_or_new(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    row = await get(session, user_id, lock=True)
    if row is None:
        row = Profile(user_id=user_id, photo_status="none", reply_lang_pref="auto")
        session.add(row)
    return row


async def active_institution(
    session: AsyncSession, institution_id: uuid.UUID
) -> Institution | None:
    row = await session.get(Institution, institution_id)
    return row if row is not None and row.is_active else None


async def district_exists(session: AsyncSession, district_id: int) -> bool:
    return await session.get(District, district_id) is not None


async def upazila_district(session: AsyncSession, upazila_id: int) -> int | None:
    row = await session.get(Upazila, upazila_id)
    return row.district_id if row is not None else None


async def districts(session: AsyncSession) -> list[tuple[District, list[Upazila]]]:
    rows = (await session.execute(select(District).order_by(District.id))).scalars().all()
    upazilas = (await session.execute(select(Upazila).order_by(Upazila.id))).scalars().all()
    by_district: dict[int, list[Upazila]] = {}
    for u in upazilas:
        by_district.setdefault(u.district_id, []).append(u)
    return [(d, by_district.get(d.id, [])) for d in rows]


def _like(q: str) -> str:
    return "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


async def search_institutions(
    session: AsyncSession, q: str | None, district_id: int | None, limit: int
) -> list[Institution]:
    """Trigram similarity on both names (plus a substring match), best first."""
    stmt = select(Institution).where(Institution.is_active.is_(True))
    if district_id is not None:
        stmt = stmt.where(Institution.district_id == district_id)
    if q:
        score = func.greatest(
            func.similarity(Institution.name_en, q), func.similarity(Institution.name_bn, q)
        )
        stmt = stmt.where(
            or_(
                Institution.name_en.op("%")(q),
                Institution.name_bn.op("%")(q),
                Institution.name_en.ilike(_like(q)),
                Institution.name_bn.ilike(_like(q)),
            )
        ).order_by(score.desc(), Institution.name_en)
    else:
        stmt = stmt.order_by(Institution.name_en)
    return list((await session.execute(stmt.limit(limit))).scalars())

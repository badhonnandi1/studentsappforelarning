"""Public reference lists: districts, institution search, consent documents (05 §D)."""

from collections.abc import Mapping
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.errors import ValidationAppError
from app.core.pagination import Page
from app.core.ratelimit import client_ip, rate_limit
from app.modules.auth.internal.repositories import profiles as repo
from app.modules.auth.internal.schemas.consent import ConsentDocumentOut, Lang
from app.modules.auth.internal.schemas.profile import (
    DistrictOut,
    DistrictsOut,
    InstitutionOut,
    UpazilaOut,
)
from app.modules.auth.internal.services import consent

router = APIRouter(prefix="/v1/reference", tags=["reference"])
documents_router = APIRouter(prefix="/v1/consent-documents", tags=["reference"])
Session = Annotated[AsyncSession, Depends(get_session)]
DAY_S = 86_400
MAX_RESULTS = 50


def _by_ip(request: Request) -> Mapping[str, str]:
    return {"user": f"ip:{client_ip(request)}"}


ReadTier = [Depends(rate_limit("read", _by_ip))]


@router.get("/districts", response_model=DistrictsOut, dependencies=ReadTier)
async def districts(response: Response, session: Session) -> DistrictsOut:
    rows = await repo.districts(session)
    await session.commit()
    response.headers["Cache-Control"] = f"public, max-age={DAY_S}"
    items = [
        DistrictOut(
            id=d.id,
            division=d.division,
            name_bn=d.name_bn,
            name_en=d.name_en,
            upazilas=[UpazilaOut.model_validate(u) for u in upazilas],
        )
        for d, upazilas in rows
    ]
    return DistrictsOut(items=items)


@router.get("/institutions", response_model=Page[InstitutionOut], dependencies=ReadTier)
async def institutions(
    session: Session,
    q: Annotated[str | None, Query(min_length=2, max_length=80)] = None,
    district_id: Annotated[int | None, Query(ge=1, le=32767)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 20,
) -> Page[InstitutionOut]:
    """Best matches first; one page only (``next_cursor`` is always null)."""
    if q is None and district_id is None:
        raise ValidationAppError("Give a search term or a district")
    rows = await repo.search_institutions(session, q.strip() if q else None, district_id, limit)
    await session.commit()
    return Page(items=[InstitutionOut.model_validate(r) for r in rows], next_cursor=None)


@documents_router.get("/{version}", response_model=ConsentDocumentOut, dependencies=ReadTier)
async def consent_document(
    response: Response,
    session: Session,
    version: Annotated[str, Path(pattern=r"^[0-9a-z-]{1,40}$")],
    lang: Lang = "bn",
) -> ConsentDocumentOut:
    out = await consent.get_document(session, version, lang)
    response.headers["Cache-Control"] = f"public, max-age={DAY_S}"  # a version never changes
    return out

"""``scripts/seed_reference.py``: the shipped CSVs load, reruns upsert, a bad row writes nothing."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules import com
from app.modules.auth.internal.models import District, Institution, Upazila
from app.modules.com.internal.repositories import terms as terms_repo
from scripts import seed_reference

pytestmark = pytest.mark.db


def seed_dir(tmp_path: Path, **extra_rows: str) -> Path:
    for name in ("districts", "upazilas", "institutions", "moderation_terms"):
        shutil.copy(seed_reference.SEED_DIR / f"{name}.csv", tmp_path / f"{name}.csv")
    for name, rows in extra_rows.items():
        with (tmp_path / f"{name}.csv").open("a", encoding="utf-8") as handle:
            handle.write(rows)
    return tmp_path


async def count(session: AsyncSession, model: type) -> int:
    value = (await session.execute(select(func.count()).select_from(model))).scalar_one()
    await session.commit()
    return int(value)


async def test_shipped_files_load_and_rerun(session: AsyncSession) -> None:
    first = await seed_reference.seed(session)
    assert first["districts"] == 64
    assert await seed_reference.seed(session) == first
    assert await count(session, District) == 64
    dhaka = await session.get(District, 26)
    await session.commit()
    assert dhaka is not None
    assert (dhaka.division, dhaka.name_bn) == ("Dhaka", "ঢাকা")


async def test_upsert_updates_in_place(session: AsyncSession, tmp_path: Path) -> None:
    rows = {
        "upazilas": "2601,26,Savar,সাভার\n",
        "institutions": "108537,Old Name,পুরনো নাম,school,26,2601\n",
        "moderation_terms": "banglish,shoytan,2,profanity\n",
    }
    await seed_reference.seed(session, seed_dir(tmp_path, **rows))
    (tmp_path / "v2").mkdir()
    changed = {**rows, "institutions": "108537,New Name,নতুন নাম,school_college,26,\n"}
    renamed = seed_dir(tmp_path / "v2", **changed)
    counts = await seed_reference.seed(session, renamed)
    assert counts["institutions"] == 1
    school = (await session.execute(select(Institution))).scalar_one()
    await session.commit()
    assert (school.name_en, school.kind, school.upazila_id) == ("New Name", "school_college", None)
    assert await count(session, Upazila) == 1
    terms_repo.invalidate()
    assert (await com.moderate(session, "Shoitan!", "post")).verdict == "block"
    terms_repo.invalidate()


@pytest.mark.parametrize(
    ("name", "row"),
    [
        ("institutions", "12AB,Bad,খারাপ,school,26,\n"),
        ("institutions", "123456,Bad,খারাপ,castle,26,\n"),
        ("moderation_terms", "fr,mot,2,profanity\n"),
        ("moderation_terms", "en,word,7,profanity\n"),
        ("moderation_terms", "en,!!!,2,profanity\n"),
        ("upazilas", "x,26,Savar,সাভার\n"),
    ],
)
async def test_bad_row_writes_nothing(
    session: AsyncSession, tmp_path: Path, name: str, row: str
) -> None:
    with pytest.raises(seed_reference.SeedError, match=f"{name}.csv:2"):
        await seed_reference.seed(session, seed_dir(tmp_path, **{name: row}))
    assert await count(session, District) == 0

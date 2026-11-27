"""Load reference data from ``backend/seed/*.csv`` with an upsert (safe to rerun).

    uv run python -m scripts.seed_reference [--seed-dir seed]

Districts and upazilas upsert on their ids. Institutions upsert on an id derived from the EIIN
(``uuid5``), so a renamed school updates in place. Moderation terms upsert on
``(lang, term_folded)``. Rows that fail validation stop the load before anything is written.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import dispose_engine, init_engine, sessionmaker
from app.core.db_base import Base
from app.core.settings import get_settings
from app.modules.auth.internal.models import District, Institution, Upazila
from app.modules.auth.internal.models.profile import INSTITUTION_KINDS
from app.modules.com.internal.models import ModerationTerm
from app.modules.com.internal.models.moderation import CATEGORIES, TERM_LANGS
from app.modules.com.internal.services.moderate import fold_term

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
EIIN_NAMESPACE = uuid.UUID("5d3f6b5e-6f1c-4c55-9b8e-0e5d7a1f2c01")


class SeedError(ValueError):
    pass


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(handle)]


def district(row: dict[str, str]) -> dict[str, Any]:
    return {"id": int(row["id"]), "division": row["division"], "name_en": row["name_en"],
            "name_bn": row["name_bn"]}  # fmt: skip


def upazila(row: dict[str, str]) -> dict[str, Any]:
    return {"id": int(row["id"]), "district_id": int(row["district_id"]),
            "name_en": row["name_en"], "name_bn": row["name_bn"]}  # fmt: skip


def institution(row: dict[str, str]) -> dict[str, Any]:
    if row["kind"] not in INSTITUTION_KINDS or not row["eiin"].isdigit():
        raise ValueError("bad kind or EIIN")
    return {"id": uuid.uuid5(EIIN_NAMESPACE, row["eiin"]), "eiin": row["eiin"],
            "name_en": row["name_en"], "name_bn": row["name_bn"], "kind": row["kind"],
            "district_id": int(row["district_id"]),
            "upazila_id": int(row["upazila_id"]) if row["upazila_id"] else None,
            "source": "seed", "is_active": True}  # fmt: skip


def term(row: dict[str, str]) -> dict[str, Any]:
    severity = int(row["severity"])
    folded = fold_term(row["lang"], row["term"]) if row["lang"] in TERM_LANGS else ""
    if not folded or row["category"] not in CATEGORIES or not 1 <= severity <= 3:
        raise ValueError("bad lang, term, category or severity")
    return {"id": uuid.uuid4(), "lang": row["lang"], "term_folded": folded, "severity": severity,
            "category": row["category"], "is_active": True}  # fmt: skip


# file, table, row parser, conflict columns (other columns are updated on conflict)
PLAN: tuple[tuple[str, type[Base], Callable[[dict[str, str]], dict[str, Any]], list[str]], ...] = (
    ("districts.csv", District, district, ["id"]),
    ("upazilas.csv", Upazila, upazila, ["id"]),
    ("institutions.csv", Institution, institution, ["id"]),
    ("moderation_terms.csv", ModerationTerm, term, ["lang", "term_folded"]),
)


def parse(seed_dir: Path) -> list[tuple[type[Base], list[dict[str, Any]], list[str]]]:
    """Read and validate every file first, so a bad row writes nothing."""
    out = []
    for name, model, parser, conflict in PLAN:
        path = seed_dir / name
        rows = []
        for line, raw in enumerate(read_rows(path), start=2):
            try:
                rows.append(parser(raw))
            except (KeyError, ValueError) as exc:
                raise SeedError(f"{path.name}:{line}: {exc}") from exc
        out.append((model, rows, conflict))
    return out


async def seed(session: AsyncSession, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    counts: dict[str, int] = {}
    plan = parse(seed_dir)
    async with session.begin():
        for model, rows, conflict in plan:
            counts[model.__tablename__] = len(rows)
            if not rows:
                continue
            stmt = insert(model).values(rows)
            keep = {c: stmt.excluded[c] for c in rows[0] if c not in (*conflict, "id")}
            await session.execute(stmt.on_conflict_do_update(index_elements=conflict, set_=keep))
    return counts


async def main(seed_dir: Path) -> None:
    init_engine(get_settings(), "worker")
    try:
        async with sessionmaker()() as session:
            counts = await seed(session, seed_dir)
    finally:
        await dispose_engine()
    for table, count in counts.items():
        print(f"{table}: {count} rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed-dir", type=Path, default=SEED_DIR)
    asyncio.run(main(parser.parse_args().seed_dir))

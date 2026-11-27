"""The seeded consent documents match the packaged static bodies (b01_10)."""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.internal.models import ConsentDocument
from app.modules.auth.internal.services.consent import DOCS

pytestmark = [pytest.mark.contract, pytest.mark.db]


async def test_every_seeded_document_has_its_file(session: AsyncSession) -> None:
    rows = (await session.execute(select(ConsentDocument))).scalars().all()
    assert {(r.version, r.lang) for r in rows} >= {("2026-11-v1", "bn"), ("2026-11-v1", "en")}
    for row in rows:
        body = (DOCS / f"{row.version}.{row.lang}.md").read_bytes()
        assert hashlib.sha256(body).digest() == row.body_sha256, (row.version, row.lang)


def test_every_file_is_a_known_document() -> None:
    names = sorted(p.name for p in DOCS.iterdir() if p.name.endswith(".md"))
    assert names == ["2026-11-v1.bn.md", "2026-11-v1.en.md"]

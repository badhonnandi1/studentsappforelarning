"""Exam ingest never loads the database stack, even indirectly (R-26)."""

from __future__ import annotations

import subprocess
import sys

import pytest

pytestmark = pytest.mark.integration

PROBE = """
import sys
import app.entrypoints.exam_ingest.main as ingest
assert ingest.app.state.service == "exam-ingest"
loaded = [m for m in ("sqlalchemy", "asyncpg", "alembic", "app.core.db") if m in sys.modules]
print(",".join(loaded) or "clean")
"""


def test_ingest_app_imports_without_postgres() -> None:
    result = subprocess.run(
        [sys.executable, "-c", PROBE], capture_output=True, text=True, check=False, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "clean"

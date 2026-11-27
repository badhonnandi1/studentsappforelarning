import subprocess
import sys

PYTHON = sys.executable

PROBE = """
import sys
import app.entrypoints.exam_ingest
loaded = sorted(m for m in ("sqlalchemy", "psycopg", "alembic", "app.core.db") if m in sys.modules)
print(",".join(loaded))
"""


def test_exam_ingest_loads_no_postgres_code(clean_env: dict[str, str]) -> None:
    result = subprocess.run(
        [PYTHON, "-c", PROBE], env=clean_env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""

#!/usr/bin/env bash
# The single gate: format, lint, types, boundaries, line limit, tests with coverage, critical-path coverage.
# Needs Postgres, Redis and MinIO running (see README.md). Extra arguments go to pytest.
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n==> %s\n' "$*"; }

step "ruff format"
uv run ruff format --check .
step "ruff check"
uv run ruff check .
step "mypy"
uv run mypy src tests scripts $([ -d migrations ] && echo migrations)
step "import-linter"
uv run lint-imports
step "module boundaries"
uv run python scripts/check_boundaries.py
step "200-line rule"
uv run python scripts/check_file_length.py
step "pytest"
uv run pytest -m "not load and not eval" -n "${PYTEST_WORKERS:-auto}" \
  --cov --cov-report=term --cov-report=json:coverage.json "$@"
step "critical-path coverage"
uv run python scripts/check_coverage_paths.py coverage.json

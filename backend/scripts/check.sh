#!/usr/bin/env bash
# Format, lint, types, module boundaries, tests. No database or Redis needed.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests migrations
uv run lint-imports
uv run pytest -q "$@"

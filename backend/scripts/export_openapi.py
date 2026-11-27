"""Write the public API's OpenAPI document to ``openapi.json`` (15 §4: the committed snapshot).

    uv run python -m scripts.export_openapi           # regenerate
    uv run python -m scripts.export_openapi --check   # exit 1 when the snapshot is stale

The app is built with default local settings (no environment file), so the output does not
depend on whoever runs it. ``tests/contract/test_openapi_snapshot.py`` runs the check in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.core.http import create_app
from app.core.settings import Settings
from app.modules.registry import all_routers

SNAPSHOT = Path(__file__).resolve().parent.parent / "openapi.json"


def document() -> dict[str, Any]:
    settings = Settings(_env_file=None, app_env="local")
    return create_app("api", routers=all_routers(), settings=settings).openapi()


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the snapshot is stale")
    args = parser.parse_args(argv)
    current = render(document())
    if args.check:
        stale = not SNAPSHOT.exists() or SNAPSHOT.read_text(encoding="utf-8") != current
        if stale:
            print("openapi.json is stale: run `uv run python -m scripts.export_openapi`")
        return 1 if stale else 0
    SNAPSHOT.write_text(current, encoding="utf-8")
    print(f"wrote {SNAPSHOT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

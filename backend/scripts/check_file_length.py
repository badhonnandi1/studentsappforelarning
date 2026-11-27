"""Fail when a handwritten file under the checked folders is longer than 200 physical lines.

Generated files are listed in scripts/line_limit_exempt.txt, one path per line, each with a reason.
"""

from __future__ import annotations

import sys
from pathlib import Path

MAX_LINES = 200
ROOT = Path(__file__).resolve().parent.parent
CHECKED_DIRS = ("src", "tests", "migrations", "scripts", "seed")
SUFFIXES = {".py", ".sh", ".sql", ".toml", ".ini", ".yml", ".yaml", ".md", ".js", ".ts"}
EXEMPT_FILE = ROOT / "scripts" / "line_limit_exempt.txt"


def load_exempt(path: Path = EXEMPT_FILE) -> set[str]:
    exempt: set[str] = set()
    if not path.exists():
        return exempt
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            exempt.add(line)
    return exempt


def too_long(root: Path = ROOT, limit: int = MAX_LINES) -> dict[str, int]:
    exempt = load_exempt(root / "scripts" / "line_limit_exempt.txt")
    found: dict[str, int] = {}
    for folder in CHECKED_DIRS:
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in SUFFIXES or "__pycache__" in path.parts:
                continue
            rel = path.relative_to(root).as_posix()
            if rel in exempt:
                continue
            count = len(path.read_text(encoding="utf-8").splitlines())
            if count > limit:
                found[rel] = count
    return found


def main() -> int:
    found = too_long()
    for rel, count in sorted(found.items()):
        print(f"{rel}: {count} lines (limit {MAX_LINES}); split it by subject")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

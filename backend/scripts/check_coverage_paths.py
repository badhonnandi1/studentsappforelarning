"""Enforce the critical-path coverage threshold from pyproject [tool.critical_coverage].

Reads the coverage.json written by pytest-cov and checks line and branch coverage for every
file that matches one of the configured globs.
"""

from __future__ import annotations

import json
import sys
import tomllib
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path = ROOT / "pyproject.toml") -> tuple[list[str], float]:
    data = tomllib.loads(path.read_text())["tool"]["critical_coverage"]
    return list(data["paths"]), float(data["threshold"])


def normalise(path: str) -> str:
    """coverage.json keys look like src/app/core/x.py; the globs start at app/."""
    marker = "app/"
    index = path.find(marker)
    return path[index:] if index >= 0 else path


def file_percent(summary: dict[str, Any]) -> float:
    statements = summary["num_statements"] + summary.get("num_branches", 0)
    covered = summary["covered_lines"] + summary.get("covered_branches", 0)
    return 100.0 if statements == 0 else 100.0 * covered / statements


def failures(report: dict[str, Any], globs: list[str], threshold: float) -> list[str]:
    found: list[str] = []
    for raw_path, data in sorted(report["files"].items()):
        path = normalise(raw_path)
        if not any(fnmatch(path, pattern) for pattern in globs):
            continue
        percent = file_percent(data["summary"])
        if percent < threshold:
            found.append(f"{path}: {percent:.1f}% < {threshold:.0f}%")
    return found


def main(argv: list[str]) -> int:
    report_path = Path(argv[1]) if len(argv) > 1 else ROOT / "coverage.json"
    globs, threshold = load_config()
    found = failures(json.loads(report_path.read_text()), globs, threshold)
    for line in found:
        print(line)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

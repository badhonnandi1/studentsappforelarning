"""The quality-gate scripts are code too: test their core logic."""

from pathlib import Path

import pytest

from scripts import check_boundaries, check_coverage_paths, check_file_length

pytestmark = pytest.mark.unit


def test_find_cycle_reports_loop() -> None:
    assert check_boundaries.find_cycle([("a", "b"), ("b", "c"), ("c", "a")]) == ["a", "b", "c", "a"]
    assert check_boundaries.find_cycle([("a", "b"), ("b", "c")]) is None


def test_real_edge_file_is_acyclic() -> None:
    edges, _ = check_boundaries.load_config()
    assert check_boundaries.find_cycle(edges) is None


def test_module_of() -> None:
    assert check_boundaries.module_of("app.modules.auth.internal.models") == "auth"
    assert check_boundaries.module_of("app.core.db") is None


def test_file_length_flags_long_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src" / "ok.py").write_text("x = 1\n" * 200)
    (tmp_path / "src" / "long.py").write_text("x = 1\n" * 201)
    (tmp_path / "src" / "gen.py").write_text("x = 1\n" * 500)
    (tmp_path / "scripts" / "line_limit_exempt.txt").write_text("src/gen.py  # generated\n")
    assert check_file_length.too_long(tmp_path) == {"src/long.py": 201}


def test_coverage_failures_apply_globs_and_branches() -> None:
    report = {
        "files": {
            "src/app/core/security/jwt.py": {
                "summary": {
                    "num_statements": 90,
                    "covered_lines": 90,
                    "num_branches": 10,
                    "covered_branches": 4,
                }
            },
            "src/app/core/other.py": {"summary": {"num_statements": 10, "covered_lines": 0}},
        }
    }
    found = check_coverage_paths.failures(report, ["app/core/security/*"], 95)
    assert found == ["app/core/security/jwt.py: 94.0% < 95%"]


def test_coverage_config_loads() -> None:
    globs, threshold = check_coverage_paths.load_config()
    assert threshold == 95
    assert "app/core/ratelimit.py" in globs

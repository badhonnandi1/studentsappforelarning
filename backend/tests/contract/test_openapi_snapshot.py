"""The committed ``openapi.json`` matches the code (15 §4): an API change ships its snapshot."""

from __future__ import annotations

import json

import pytest

from scripts import export_openapi

pytestmark = pytest.mark.contract


def test_snapshot_is_current() -> None:
    assert export_openapi.main(["--check"]) == 0, "run: uv run python -m scripts.export_openapi"


def test_snapshot_shape() -> None:
    doc = json.loads(export_openapi.SNAPSHOT.read_text(encoding="utf-8"))
    assert doc["info"]["title"] == "studyplatform-api"
    paths = doc["paths"]
    for path in ("/v1/auth/otp/send", "/v1/auth/refresh", "/v1/me", "/v1/reports", "/readyz"):
        assert path in paths
    assert not any(p.startswith("/v1/test") for p in paths)  # no test-only routes leak in

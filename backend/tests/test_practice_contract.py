from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.entrypoints.api import app
from app.modules.prac.contracts import SaveAnswerRequest, SaveAnswerResponse

ANSWER_ID = "0193a7c4-5e1f-7b3a-9c21-4d6f8a1b2c3d"

# v2 §3.2 sample, with the elided ids filled in.
REQUEST = {
    "answer_id": ANSWER_ID,
    "question_version_id": "0192f1aa-0000-7000-8000-000000000001",
    "lang": "bn",
    "response": {"selected": ["kha"]},
    "time_spent_ms": 41200,
    "answered_at": "2026-11-26T17:58:03Z",
    "client": {"monotonic_since_sync_ms": 512300, "last_server_sync": "2026-11-26T17:49:31Z"},
}


def test_sample_request_parses() -> None:
    req = SaveAnswerRequest.model_validate(REQUEST)
    assert req.answer_id == UUID(ANSWER_ID)
    assert req.response.selected == ["kha"]


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": 1},
        {"answered_at": "2026-11-26T17:58:03"},  # no timezone
        {"lang": "fr"},
        {"time_spent_ms": -1},
    ],
)
def test_invalid_requests_are_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SaveAnswerRequest.model_validate(REQUEST | change)


def test_learn_mode_response_matches_sample() -> None:
    resp = SaveAnswerResponse(
        answer_id=UUID(ANSWER_ID),
        duplicate=False,
        is_correct=False,
        answer_key={"correct": ["ga"]},
        explanation_html="…",
        effective_at=datetime.fromisoformat("2026-11-26T17:58:03+00:00"),
        xp_awarded=2,
    )
    assert resp.model_dump(mode="json", exclude_none=True)["answer_key"] == {"correct": ["ga"]}


def test_test_mode_response_has_only_id_and_duplicate() -> None:
    resp = SaveAnswerResponse(answer_id=UUID(ANSWER_ID), duplicate=True)
    assert resp.model_dump(mode="json", exclude_none=True) == {
        "answer_id": ANSWER_ID,
        "duplicate": True,
    }


def test_contract_is_not_wired_to_a_route_yet() -> None:
    paths = {getattr(route, "path", "") for route in app.routes}
    assert not any(path.startswith("/v1/practice") for path in paths)

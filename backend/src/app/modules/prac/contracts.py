"""PRAC public contract: save a practice answer (v2 §3.2, §3.5).

    POST /v1/practice/sessions/{session_id}/answers
    Authorization: Bearer <access JWT>
    Idempotency-Key: <answer_id>

This is the typed example of where a feature contract lives. It is deliberately
NOT wired to a route yet; the router will sit next to it when PRAC is built.

Rules the handler must enforce (v2 §3.2, §3.5):
- ``answer_id`` is generated on the device and is also the Idempotency-Key.
- Uniqueness is on ``(user_id, answer_id)``: a replay by the same user returns the
  stored result with ``duplicate=true`` and HTTP 200; the same id from a different
  user is rejected with HTTP 409.
- The answer, notebook, progress, XP ledger, streak day and outbox row commit in
  one transaction.
- In Test mode the response carries only ``answer_id`` and ``duplicate``.
"""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ClientClock(_Contract):
    """Device timing used to compute ``effective_at`` for offline answers (v2 §5.5)."""

    monotonic_since_sync_ms: int = Field(ge=0)
    last_server_sync: AwareDatetime


class McqResponse(_Contract):
    """MCQ response, e.g. ``{"selected": ["kha"]}``.

    First member of the per-question-type response union (QB-01); other types
    (numeric, matching, fill-in, ...) are added here as they are built.
    """

    selected: list[str] = Field(min_length=1)


AnswerResponse = McqResponse


class McqAnswerKey(_Contract):
    """Correct options, e.g. ``{"correct": ["ga"]}``. Shown only in Learn mode."""

    correct: list[str] = Field(min_length=1)


class SaveAnswerRequest(_Contract):
    answer_id: UUID
    question_version_id: UUID
    lang: Literal["bn", "en"]
    response: AnswerResponse
    time_spent_ms: int = Field(ge=0)
    answered_at: AwareDatetime
    client: ClientClock


class SaveAnswerResponse(_Contract):
    """Learn-mode fields are optional; Test mode returns only ``answer_id`` and ``duplicate``.

    Serialise with ``model_dump(exclude_none=True)``.
    """

    answer_id: UUID
    duplicate: bool
    is_correct: bool | None = None
    answer_key: McqAnswerKey | None = None
    explanation_html: str | None = None
    effective_at: AwareDatetime | None = None
    xp_awarded: int | None = Field(default=None, ge=0)

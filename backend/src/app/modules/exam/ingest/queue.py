"""Exam-answer batch queue: SQS Standard in staging/prod, in-memory locally (v2 §0.2).

SQS is reserved for exam-answer batches; all other background work uses the
Postgres job queue (app.modules.nfr.jobqueue). Batches are idempotent on
``(attempt_id, seq)``, so at-least-once delivery from SQS Standard is safe.
"""

from collections import deque
from typing import Any, Protocol

from app.core.settings import Settings


class AnswerBatchQueue(Protocol):
    name: str

    def send(self, batch: dict[str, Any]) -> None: ...


class InMemoryAnswerBatchQueue:
    """Local and test stand-in. Not durable; never used in staging or prod."""

    name = "memory"

    def __init__(self) -> None:
        self._items: deque[dict[str, Any]] = deque()

    def send(self, batch: dict[str, Any]) -> None:
        self._items.append(batch)

    def receive(self, max_messages: int = 10) -> list[dict[str, Any]]:
        return [self._items.popleft() for _ in range(min(max_messages, len(self._items)))]


class SqsAnswerBatchQueue:
    """SQS Standard adapter. The live AWS integration is deferred."""

    name = "sqs"

    def __init__(self, queue_url: str, region: str) -> None:
        self.queue_url = queue_url
        self.region = region

    def send(self, batch: dict[str, Any]) -> None:
        raise NotImplementedError("SQS integration is deferred (exam ingest prototype, v2 §8.1)")


def build_queue(settings: Settings) -> AnswerBatchQueue:
    if settings.exam_answer_queue_backend == "sqs":
        if not settings.exam_answer_queue_url:  # Settings validation already refuses this
            raise ValueError("EXAM_ANSWER_QUEUE_URL is required for the sqs backend")
        return SqsAnswerBatchQueue(settings.exam_answer_queue_url, settings.aws_region)
    return InMemoryAnswerBatchQueue()

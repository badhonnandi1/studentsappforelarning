"""exam-ingest deployable: exam answer intake and durable acknowledgement (v2 §6.2).

Run: uv run uvicorn app.entrypoints.exam_ingest:app --port 8002

Touches only Redis and the exam-answer queue (SQS Standard), never PostgreSQL.
import-linter enforces this; see .importlinter.
"""

from app.core.http import create_app
from app.core.redis import ping_redis
from app.core.settings import get_settings
from app.modules.exam.ingest.queue import build_queue

# Readiness checks Redis only: exam-ingest never depends on PostgreSQL.
app = create_app("exam-ingest", ready_checks={"redis": ping_redis})
answer_queue = build_queue(get_settings())

"""Exam answer ingest: ``uvicorn app.entrypoints.exam_ingest.main:app``.

Never imports ``app.core.db``, SQLAlchemy or asyncpg (import-linter and a subprocess test).
Routes arrive in B5.
"""

from app.core.http import create_app
from app.core.redis import ping_redis
from app.entrypoints.boot import light_lifespan

app = create_app(
    "exam-ingest",
    routers=[],
    ready_checks={"redis": ping_redis},
    lifespan=light_lifespan("exam-ingest"),
)

"""api deployable: synchronous APIs of all server-owned modules (v2 §2.1).

Run: uv run uvicorn app.entrypoints.api:app --port 8000

Feature routers are mounted here as modules are built, e.g.
``app.include_router(prac_router, prefix="/v1/practice")``. None are mounted yet.
"""

from app.core.db import ping_db
from app.core.http import create_app
from app.core.redis import ping_redis

app = create_app("api", ready_checks={"db": ping_db, "redis": ping_redis})

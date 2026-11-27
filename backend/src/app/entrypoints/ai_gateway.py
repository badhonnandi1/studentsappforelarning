"""ai-gateway deployable: tutor streaming, provider calls, circuit breakers (v2 §2.1, §4).

Run: uv run uvicorn app.entrypoints.ai_gateway:app --port 8001

The tutor SSE route (POST /v1/tutor/messages) from app.modules.ai is mounted here
when AI is built. No provider is called yet (AI_PROVIDER=none).
"""

from app.core.db import ping_db
from app.core.http import create_app
from app.core.redis import ping_redis

app = create_app("ai-gateway", ready_checks={"db": ping_db, "redis": ping_redis})

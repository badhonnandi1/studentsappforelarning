"""AI gateway: ``uvicorn app.entrypoints.ai_gateway.main:app``. Routes arrive in B4."""

from app.core.http import create_app
from app.entrypoints.stack import READY_CHECKS, db_lifespan

app = create_app(
    "ai-gateway", routers=[], ready_checks=READY_CHECKS, lifespan=db_lifespan("ai-gateway")
)

"""The public API: ``uvicorn app.entrypoints.api.main:app``."""

from app.core.http import create_app
from app.entrypoints.stack import READY_CHECKS, db_lifespan
from app.modules.registry import all_routers

app = create_app(
    "api", routers=all_routers(), ready_checks=READY_CHECKS, lifespan=db_lifespan("api")
)

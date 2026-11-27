# One image for every deployable; the command picks the entry point:
#   api:            uvicorn app.entrypoints.api.main:app --host 0.0.0.0 --port 8000
#   workers:        python -m app.entrypoints.workers.main
#   ai-gateway:     uvicorn app.entrypoints.ai_gateway.main:app --host 0.0.0.0 --port 8000
#   exam-ingest:    uvicorn app.entrypoints.exam_ingest.main:app --host 0.0.0.0 --port 8000
#   exam-consumers: python -m app.entrypoints.exam_consumers.main
FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
RUN uv sync --frozen --no-dev

FROM python:3.13-slim
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
CMD ["uvicorn", "app.entrypoints.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

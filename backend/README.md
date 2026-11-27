# Backend

This is the runnable skeleton of the modular monolith described in [`docs/system-design-v2.md`](../docs/system-design-v2.md) (§0.2, §2.1–2.4, §3). It is built on the conventions of the team's `fastapi-starter` and uses one Python 3.13 / FastAPI codebase with five entry points, and each of the 16 server-owned modules has its own package and PostgreSQL 17 schema.

What runs today:
- `GET /livez` and `GET /readyz` on the three HTTP apps. `/readyz` checks only the stores that app uses (exam-ingest checks Redis, never PostgreSQL).
- A startup check on the two workers.
- One migration that creates the 16 module schemas.
- import-linter contracts that enforce the module boundaries.

Business logic, tables, live integrations (SQS, LLM, SMS, payments), frontend and deployment are not built yet.

## Folder tree

```
backend/
├── pyproject.toml            dependencies, scripts, ruff / mypy strict / pytest config
├── uv.lock                   locked versions
├── .python-version           3.13
├── .env.example              every setting, with working local defaults
├── .importlinter             module-boundary contracts (v2 §2.2)
├── alembic.ini
├── scripts/check.sh          format, lint, types, import contracts, tests
├── docker-compose.yml        local PostgreSQL 17 + Redis only (not deployment)
├── migrations/
│   ├── env.py                reads DATABASE_URL from app settings
│   └── versions/0001_module_schemas.py   CREATE SCHEMA for the 16 module schemas
├── src/app/
│   ├── core/                 shared kernel; imports no feature module
│   │   ├── settings.py       environment-based settings (pydantic-settings)
│   │   ├── http.py           FastAPI factory: /livez, /readyz, request ids, error handlers
│   │   ├── db.py             PostgreSQL engine/sessions (SQLAlchemy 2 + psycopg 3)
│   │   ├── redis.py          Redis client
│   │   ├── worker.py         --check / idle-loop runner for non-HTTP deployables
│   │   ├── errors.py         AppError → JSON error responses (from fastapi-starter)
│   │   └── logging.py        structlog + X-Request-ID middleware (from fastapi-starter)
│   ├── shared/               money, bd_phone, dhaka_date, types (copied from fastapi-starter)
│   ├── entrypoints/          one file per deployable (v2 §2.1)
│   │   ├── api.py            all modules' synchronous APIs
│   │   ├── ai_gateway.py     tutor streaming, provider calls
│   │   ├── exam_ingest.py    exam answer intake (Redis + queue only)
│   │   ├── workers.py        Postgres job runner
│   │   └── exam_consumers.py SQS answer consumers and scorer
│   └── modules/
│       ├── registry.py       the 17 modules: code → package → schema; OFF client-owned
│       ├── auth/  tax/  qb/  cms/  anl/  ai/  gam/  plan/
│       ├── com/   par/  inst/ pay/ ops/          each: __init__.py (public) + internal/ (private)
│       ├── prac/
│       │   ├── __init__.py
│       │   ├── contracts.py  typed "save practice answer" contract (v2 §3.2), not routed yet
│       │   └── internal/
│       ├── exam/
│       │   ├── __init__.py
│       │   ├── ingest/       served by exam-ingest; queue.py = SQS / in-memory adapter
│       │   ├── consumers/    served by exam-consumers
│       │   └── internal/
│       └── nfr/
│           ├── __init__.py
│           ├── outbox.py     transactional outbox (placeholder)
│           ├── jobqueue.py   Postgres job queue (placeholder)
│           └── internal/
└── tests/                    health, worker startup, modules, ingest isolation, contract,
                              shared types, 200-line file limit
```

## Module → schema

Each module's `__init__.py` is its public interface and declares `CODE` and `SCHEMA`. Its `internal/` package holds models, queries and services, and no other module may import it.

| Code | Package | PostgreSQL schema | Responsibility |
|---|---|---|---|
| AUTH | `app.modules.auth` | `identity` | Accounts, sessions, roles, profiles, enrolments, consent |
| TAX | `app.modules.tax` | `curriculum` | Tracks, taxonomy tree, syllabus versions |
| QB | `app.modules.qb` | `qbank` | Questions, versions, translations, papers, imports, duplicates |
| CMS | `app.modules.cms` | `cms` | Editor, workflow, review queues, error reports |
| PRAC | `app.modules.prac` | `practice` | Sessions, answers, notebook, bookmarks, notes |
| EXAM | `app.modules.exam` | `exam` | Blueprints, exams, registration, attempts, results, merit |
| ANL | `app.modules.anl` | `analytics` (+ S3 event log) | Progress, readiness, weak areas, analytics models |
| AI | `app.modules.ai` | `ai` | Tutor, retrieval, OCR, routing, cache, evals |
| GAM | `app.modules.gam` | `rewards` (+ Redis) | XP ledger, levels, streaks, leaderboards |
| PLAN | `app.modules.plan` | `notify` | Countdowns, notification centre, delivery |
| COM | `app.modules.com` | `community` | Moderation at P0; threads and doubts later |
| PAR | `app.modules.par` | `parent` | Parent views and controls (P1) |
| INST | `app.modules.inst` | `institution` | Workspaces, rosters, private bank, batch exams (P1) |
| PAY | `app.modules.pay` | `commerce` | Catalogue, orders, payments, entitlements, refunds |
| OPS | `app.modules.ops` | `ops` | Admin console, control room, tickets, banners, audit |
| NFR | `app.modules.nfr` | `platform` | Outbox, job queue, idempotency keys, search, observability |
| OFF | *none (client-owned)* | device storage | Android/PWA client, lite mode, sync engine. Built in the React Native client, not here |

## Where the infrastructure belongs

| Piece | Location | Used by |
|---|---|---|
| PostgreSQL 17 (system of record) | `app/core/db.py`, `migrations/` | api, workers, exam-consumers. **Never exam-ingest.** |
| Redis (limits, quotas, leaderboards, exam locks, caches) | `app/core/redis.py` | api, ai-gateway, exam-ingest, workers, exam-consumers |
| Transactional outbox | `app/modules/nfr/outbox.py`, written in the caller's transaction | every module that emits events |
| Postgres job queue (`FOR UPDATE SKIP LOCKED`) | `app/modules/nfr/jobqueue.py` | `workers` |
| SQS Standard, **exam-answer batches only** | `app/modules/exam/ingest/queue.py` (`EXAM_ANSWER_QUEUE_BACKEND=memory` locally) | exam-ingest (send), exam-consumers (receive) |
| Practice-answer contract (v2 §3.2) | `app/modules/prac/contracts.py` | the future PRAC router in `api` |

## Boundary rules (`uv run lint-imports`)

There are 18 contracts:
1. **Layers.** `entrypoints` → `modules` → `core` → `shared`. A layer may import the layers below it, never above.
2. **No PostgreSQL in exam-ingest.** `entrypoints.exam_ingest` and `modules.exam.ingest` must not import `app.core.db`, `sqlalchemy`, `psycopg` or `alembic`, even indirectly. `tests/test_exam_ingest_isolation.py` checks the same thing at runtime.
3. **Private internals (16 contracts).** No module may import another module's `internal/`.

## Commands

Run all commands from `backend/`. You need [uv](https://docs.astral.sh/uv/); it installs Python 3.13 if it is missing.

```bash
# Install
uv sync
cp .env.example .env            # optional: every setting has a local default

# Run the HTTP apps (each in its own terminal)
uv run uvicorn app.entrypoints.api:app --reload --port 8000
uv run uvicorn app.entrypoints.ai_gateway:app --reload --port 8001
uv run uvicorn app.entrypoints.exam_ingest:app --reload --port 8002
curl localhost:8000/livez       # {"status":"ok","service":"api"}
curl localhost:8000/readyz      # 200 with "db":"ok","redis":"ok", or 503 naming what is down

# Run the workers
uv run workers --check          # startup check, exits 0
uv run exam-consumers --check
uv run workers                  # idle loop (no handlers yet); Ctrl+C stops it cleanly

# Check everything (no database or Redis needed)
scripts/check.sh                # ruff format, ruff, mypy strict, lint-imports, pytest
uv run pytest tests/test_health.py   # one file
```

### Database (optional; nothing above needs it)

```bash
docker compose up -d postgres redis        # needs the Docker Compose plugin
# without Compose:
#   docker run -d --name studyplatform-pg -e POSTGRES_USER=app -e POSTGRES_PASSWORD=app \
#     -e POSTGRES_DB=app -p 5432:5432 postgres:17
uv run alembic upgrade head                # creates the 16 module schemas
uv run alembic upgrade head --sql          # print the SQL without a database
uv run alembic downgrade base
```

## Conventions from fastapi-starter

- Services raise `app.core.errors` subclasses (`ConflictError` for an `answer_id` reused by another user); routes never build error responses.
- Python files stay under 200 lines (`tests/test_structure.py`); split by subject.
- pytest treats warnings as errors.
- `src/app/shared/{money,bd_phone,dhaka_date}.py` are byte-identical copies of the starter's; fix them there and recopy. Note that v2 §3.1 stores money as integer poisha, while `Money` is a 2-decimal `Decimal`. Decide which wins before building PAY.

## Where feature work starts

Take PRAC as the example:
1. Add tables in `modules/prac/internal/` (schema `practice`) with an Alembic migration.
2. Add a router next to `contracts.py` and mount it in `entrypoints/api.py`.
3. Write the outbox row through `modules/nfr/outbox.py` in the same transaction.

Every other module follows the same pattern inside its own package.

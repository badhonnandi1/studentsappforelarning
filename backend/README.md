# Study platform backend

A FastAPI modular monolith: Python 3.13, PostgreSQL 17, Redis 7, and S3-compatible storage
(MinIO locally). Build 1 (platform and identity) is implemented. What it covers, with every
decision and deviation, is in [`BUILD_01_REPORT.md`](BUILD_01_REPORT.md). The specification is
[`../docs/implementation/05_build_01.md`](../docs/implementation/05_build_01.md).

## Run locally

```bash
uv sync                                   # dependencies into .venv (uv ≥ 0.9)
docker compose up -d                      # or: scripts/dev_services.sh up (no compose plugin)
cp .env.example .env
uv run python scripts/dev_keys.py         # paste the printed values into .env
uv run alembic upgrade head               # as app_migrator
uv run python -m scripts.seed_reference   # districts (+ upazilas, institutions, terms when filled)
uv run python -m scripts.seed_dev         # local only: admin, test students, an admin token
uv run uvicorn app.entrypoints.api.main:app --reload
uv run python -m app.entrypoints.workers.main --queues sms,maintenance,default
```

- **Local ports:** Postgres 55432, PgBouncer 56432, Redis 56379, MinIO 59000. They bind to 127.0.0.1 only.
- **Health:** `/livez` checks only that the process is up. `/readyz` checks Postgres and Redis, 2 s each.
- **API docs:** served at `/docs` in local and test. They are switched off in staging and prod.
- **Test OTP:** phones in the reserved block `+8801700000000`–`+8801700009999` never reach an SMS gateway. With `TEST_PHONE_OTP` set, they accept that fixed code, and only when `APP_ENV` is `local` or `test`.
- **Seeded admin:** `seed_dev` refuses to run outside `local` and `test`. It prints a 15-minute admin token from a real `sso` session.

## Deployables

All of them come from one image (see the `Dockerfile` header):

| Process | Command |
|---|---|
| api | `uvicorn app.entrypoints.api.main:app` |
| workers | `python -m app.entrypoints.workers.main --queues …` (jobs, outbox relay, scheduler) |
| ai-gateway, exam-ingest, exam-consumers | stubs until builds 4 and 5 |

The configuration is validated at start-up. Staging and prod refuse unsafe settings: debug on, wildcard CORS, the fake SMS backend, the memory queue, local KMS, a test OTP, dev staff tokens, a missing CAPTCHA, missing social secrets, and short keys.

## Test and the gate

```bash
scripts/check.sh                          # the single gate, also run by CI
uv run pytest tests/modules/auth -n 0     # one area
uv run python -m scripts.export_openapi   # after any API change: refresh openapi.json
```

`check.sh` runs these steps in order:
1. `ruff format --check` and `ruff check`.
2. `mypy` in strict mode.
3. import-linter and `check_boundaries.py`.
4. The 200-line rule.
5. `pytest` with branch coverage.
6. The critical-path coverage gate.

The tests need the local services running. Each xdist worker gets its own cloned, migrated database and Redis index, and each test runs in a rolled-back transaction. `tests/contract/test_openapi_snapshot.py` fails whenever the committed `openapi.json` is stale.

**Coverage:** at least 85% overall and 95% on the critical paths listed under `[tool.critical_coverage]` in `pyproject.toml`: security, tokens, providers, idempotency, the outbox, jobs, and audit.

**CI** (`.github/workflows/backend.yml`) runs five jobs: lint, test (pg17, Redis 7, MinIO), a migration round-trip, security (pip-audit, gitleaks, trivy), and an image build.

## Layout

```text
src/app/core/          settings, db, redis, http (middleware), errors, logging, security, ratelimit
src/app/modules/<m>/   one package per module (registry.py lists all 16)
  __init__.py          the public surface; other modules import only this and contracts/
  contracts/           DTOs, events and protocols shared with other modules
  internal/            models, repositories, services, routes, schemas (private)
src/app/entrypoints/   api, workers, ai_gateway, exam_ingest, exam_consumers
migrations/            Alembic; one revision per build step (b01_NN)
scripts/               gate, seeds, dev keys, OpenAPI export
seed/                  reference CSVs (see seed/README.md)
tests/                 mirrors src/; support/ holds fakes, factories and token helpers
```

## Conventions

- **Layers:** routes → services → repositories → models. Services own the transaction (`async with session.begin()`) and never import FastAPI. Redis side effects run after commit.
- **Module edges:** `scripts/module_edges.toml` lists which modules may import which. `check_boundaries.py` enforces the list and keeps other modules out of `internal/`.
- **Writes that matter:** they go through `ops.audited(...)`. `audit_log` is append-only: `app_rw` has SELECT and INSERT only.
- **Retried POSTs:** POSTs the client may retry take an `Idempotency-Key` (`nfr.idempotent`). A replay returns the stored response.
- **Errors:** every error uses one envelope, `{"error": {"code", "message", "details", "request_id"}}`.
- **Pagination:** opaque cursors (`core/pagination.py`). There are no offsets.
- **PII:**
  - Phone, email and guardian phone are stored encrypted (AES-GCM, KMS-wrapped keys), with keyed hashes for lookup.
  - Logs redact sensitive keys and mask phone numbers and emails found in free text.
  - Rate-limit keys are hashed.
  - Provider access tokens are never stored.
- **Money:** integer poisha. **Time:** UTC `timestamptz`, with an injected `Clock` in services.
- **Files:** ≤ 200 lines each. `scripts/line_limit_exempt.txt` lists the generated exceptions.

## HTTP hardening

These come from `core/http.py` and `core/middleware.py`:
- **Middleware order, outermost first:**
  1. request context (request id, trace id, access log);
  2. security headers (HSTS, nosniff, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Content-Security-Policy: default-src 'none'`, and `Cache-Control: no-store` unless a route sets its own);
  3. CORS;
  4. body limit;
  5. GZip.
- **CORS:** only the origins in `CORS_ORIGINS`, and only the request headers the API reads. No credentials are allowed.
- **Body limit:** 256 KB by default and 1 MB on batch endpoints, checked against `Content-Length` and against the streamed body. Uploads go straight to S3 through presigned URLs.
- **Rate limits:** each route has its own tier through a dependency (`core/ratelimit.py`). The limits can be overridden at runtime through `ratelimit.overrides`.

# Build 1 · Platform foundation, identity & safety

| Item | Value |
|---|---|
| Status | Planned · not started |
| Depends on | Nothing (first build). The repository holds only the empty skeleton folders from commit `acb5cbb`. |
| Estimated effort | 9–12 backend person-weeks ([04 §6.3](04_backend_master_plan.md)) |
| Feature IDs | P0: AUTH-01 (phone OTP, Google, Facebook), AUTH-02, AUTH-03, AUTH-04, COM-05, OPS-04. Foundations of NFR-05, NFR-06, NFR-07, NFR-08, NFR-09 and OPS-07 (kill switches only). |
| Next build | [06_build_02.md](06_build_02.md) |

---

## 0. How to run this build

**Read first, in this order:**
1. [`README.md`](README.md)
2. [`04_backend_master_plan.md`](04_backend_master_plan.md): the whole document (layout, layering, communication rules, patterns).
3. This document.
4. [`01_database_design.md`](01_database_design.md): §1, §3.1, §3.2, §3.3, §3.4 (`sms_messages`, `templates`), §3.5 (`audit_log`), §3.17, §5.
5. [`14_api_contracts.md`](14_api_contracts.md): §1, §2, and the B1 rows in §3.1, §3.2, §3.3 and §3.16.
6. [`15_testing_and_quality_standards.md`](15_testing_and_quality_standards.md) and [`18_security_architecture.md`](18_security_architecture.md).

**Preconditions:**
- `main` is at or after `acb5cbb`, and `backend/` contains only `.gitkeep` folders.
- Python 3.13, `uv` ≥ 0.5, Docker and Node 20 (Node is only for pre-commit hooks that need it; KaTeX starts in B2).

**Branch:** `build/01-platform-identity`

**Commands, once the step that creates them is done:**
```bash
cd backend
uv sync                         # creates .venv from uv.lock
docker compose up -d            # postgres (pgvector), redis, localstack
uv run alembic upgrade head
scripts/check.sh                # format, lint, mypy, boundaries, line limit, tests, coverage
uv run pytest -m "not load"     # the full non-load suite
uv run pre-commit install
```

**Stop rule.** Stop when every §F exit criterion holds and the PR is open. Do not start Build 2, and do not create anything for the frontend.

---

## A. Overview

| Item | Detail |
|---|---|
| Name | Platform foundation, identity & safety |
| Objective | A runnable, fully tooled backend. All five deployables boot with health checks, and every cross-cutting mechanism later builds rely on exists and is tested: outbox, job queue, idempotency, rate limits, audit, kill switches, partition maintenance, PII encryption. Users can sign in by phone OTP, Google or Facebook, manage sessions, fill a profile, record guardian consent and be moderated. |
| Business value | Accounts exist from the first pilot day. Social sign-in cuts OTP SMS cost (the pilot SMS line in v2 §8.6 is US$200 a month). Consent and privacy defaults satisfy NFR-07 before any minor's data is collected. |
| Technical value | Proves the module layout, import boundaries, the 200-line rule and the test harness on real Postgres before any domain logic lands. Later builds add modules without touching the foundation. |
| Modules | NFR (`platform`), OPS (`ops`), AUTH (`identity`), COM (`community`), PLAN (`notify`: SMS and templates only) |
| Dependencies | None internal. External: an SMS gateway sandbox account, a Google OAuth client (Android, web and iOS client ids), a Facebook app (app id and secret), and localstack for SQS and S3 locally. |
| Complexity | 3/5 |
| Effort | 9–12 pw |

**Features**

| ID | Scope in this build |
|---|---|
| AUTH-01 | Phone OTP (+88) sign-up and sign-in; Google sign-in; Facebook sign-in (user-approved scope change); account linking and unlinking. Apple and email/password are in B8. |
| AUTH-02 | Device sessions listed and revocable; rotating refresh tokens with reuse detection; `exam_epoch` column ready for B5's single-session enforcement |
| AUTH-03 | Eight roles, permissions, scoped grants, `can(actor, action, resource)` |
| AUTH-04 | Profile (class, group, version, curriculum, institution, district, upazila, board, exam year, photo) and the district, upazila and institution reference lists |
| COM-05 | `moderate(text, context)` (Bangla/English/Banglish term filter), reports, mute and ban, all audited |
| OPS-04 | `ops.audit_log` with the `audited()` wrapper; audit search API |
| OPS-07 (P0 part) | `platform.runtime_config` kill switches and minimum app version |
| NFR-05 (foundation) | Bilingual message templates with Bangla numerals; `Accept-Language` handling |
| NFR-06 (foundation) | OTP abuse controls, rate limiting, PII envelope encryption, keyed hashes, security headers, CORS |
| NFR-07 (foundation) | Age from date of birth, guardian OTP consent, private-by-default privacy settings, leaderboard opt-out flag |
| NFR-08 (foundation) | structlog JSON logs, request and trace ids, OpenTelemetry metrics and traces, health endpoints |
| NFR-09 (foundation) | Outbox, Postgres job queue, relay to S3 Parquet (no domain events yet besides auth events) |

**Risks and blockers**

| Risk | Mitigation |
|---|---|
| SMS vendor contract not ready | Fake SMS adapter (writes to `notify.sms_messages` with status `fake_sent` and logs the code in local and test only). The real adapter is behind a settings flag. |
| Facebook app review takes weeks | Development uses test users in development mode. Production login needs only the `public_profile` and `email` permissions. Meta lists both under "Permissions That Do Not Require Review" (checked 2026-11-27). New Consumer apps are auto-approved for Advanced Access to both, but the dashboard starts them at Standard Access, which only works for people with a role on the app. Before launch: switch both to Advanced Access, put the app in Live mode, and complete the annual Data Use Checkup. Whether Business Verification is also required for this case is still **[Needs evidence: check in the App Dashboard when the app is created]**. |
| asyncpg prepared statements under PgBouncer | Default `statement_cache_size=0`; a staging test with PgBouncer in transaction mode is an exit criterion. |
| Over-building infrastructure | Each mechanism is built only to the level the B1 tests exercise; for example, the relay writes Parquet, but partition-aware parallel relays wait for load evidence (B9). |

---

## B. Database implementation

### B.1 Tables to create

All column definitions are in [01 §4](01_database_design.md) under each schema; the key columns are in 01 §3.

| Schema | Tables | 01 ref |
|---|---|---|
| `platform` | `outbox` (P, daily), `jobs`, `dead_jobs`, `processed_events` (P, daily), `idempotency_keys`, `runtime_config`, `relay_checkpoints` | §3.1 |
| `identity` | `users`, `external_identities`, `otp_challenges`, `device_sessions`, `refresh_tokens`, `roles`, `permissions`, `role_permissions`, `role_grants`, `profiles`, `districts`, `upazilas`, `institutions`, `consent_documents`, `guardian_consents`, `privacy_settings`, `data_requests` | §3.2 |
| `community` | `moderation_terms`, `moderation_decisions`, `content_reports`, `user_restrictions` | §3.3 |
| `notify` | `sms_messages` (P, monthly), `templates` | §3.4 |
| `ops` | `audit_log` (P, monthly) | §3.5 |

There are no tables to modify, since this is the first build. `platform.search_documents` waits for B2, and `identity.track_enrolments` waits for B2 because it needs TAX.

### B.2 Relationships, indexes and constraints

- `external_identities.user_id`, `device_sessions.user_id`, `role_grants.user_id`, `profiles.user_id`, `guardian_consents.user_id`, `privacy_settings.user_id`, `user_restrictions.user_id` → `identity.users(id)` `ON DELETE RESTRICT` (users are never hard-deleted).
- `refresh_tokens.session_id` → `device_sessions(id)` `ON DELETE CASCADE`.
- `profiles.institution_id` → `institutions(id)`; `profiles.district_id` → `districts(id)`; `upazilas.district_id` → `districts(id)`.
- `role_permissions` → `roles(code)` and `permissions(code)`.
- Key uniques:
  - `users.phone_hash` (partial, not null); `users.email_hash` (partial).
  - `external_identities (provider, provider_subject)`, plus partial `(user_id, provider) WHERE unlinked_at IS NULL`.
  - `refresh_tokens.token_hash`.
  - `role_grants` partial uq on active grants.
  - `moderation_terms (lang, term_folded)`.
  - `jobs.dedupe_key` (partial).
- Key indexes:
  - `jobs (queue, priority DESC, run_at) WHERE locked_until IS NULL`, for the claim query.
  - `outbox (recorded_at) WHERE relayed_at IS NULL`, per partition.
  - `otp_challenges (phone_hash, created_at DESC)`.
  - `device_sessions (user_id) WHERE revoked_at IS NULL`.
  - `institutions` GIN trigram on `name_bn` and `name_en`.
  - `audit_log (target_type, target_id)` and `(actor_user_id, occurred_at)`.
- Checks:
  - every enum-like `text` has a `CHECK (… IN (…))`;
  - `otp_challenges.attempts <= 5`;
  - `users.status IN ('active','suspended','pending_deletion','deleted')`;
  - `external_identities.provider IN ('google','facebook','apple')`.
  - `apple` is allowed now so B8 needs no constraint swap.
- Privileges: the migration role owns all tables. The application role `app_rw` gets `SELECT, INSERT` only on `ops.audit_log` (no `UPDATE` or `DELETE`), and full DML elsewhere.

### B.3 Migration sequence

Revisions live in `backend/migrations/versions/`. Each file stays under 200 lines.

| Revision | Content |
|---|---|
| `b01_01_extensions_schemas` | `CREATE EXTENSION` vector, pg_trgm, ltree, btree_gist, pgcrypto. All 16 schemas from `modules/registry.py`. Roles `app_rw` and `app_migrator` with grants. |
| `b01_02_partition_helpers` | SQL functions created from `migrations/helpers/partitions.py`: `platform.create_range_partitions(table, period, ahead)`. Called from later migrations and the maintenance job. |
| `b01_03_platform_queue` | `jobs`, `dead_jobs`, `runtime_config`, `relay_checkpoints`, `idempotency_keys` |
| `b01_04_platform_outbox` | `outbox` and `processed_events` as partitioned parents, plus 7 days of partitions ahead |
| `b01_05_ops_audit` | `audit_log` partitioned monthly, 3 months ahead; privileges |
| `b01_06_identity_core` | `users`, `external_identities`, `otp_challenges` |
| `b01_07_identity_sessions` | `device_sessions`, `refresh_tokens` |
| `b01_08_identity_rbac` | `roles`, `permissions`, `role_permissions`, `role_grants`, plus seed data (8 roles, the permission list in C.6) |
| `b01_09_identity_reference` | `districts`, `upazilas`, `institutions` (empty; seeded by script) |
| `b01_10_identity_profile_consent` | `profiles`, `consent_documents`, `guardian_consents`, `privacy_settings`, `data_requests` |
| `b01_11_notify_sms` | `sms_messages` (partitioned), `templates` |
| `b01_12_community_moderation` | `moderation_terms`, `moderation_decisions`, `content_reports`, `user_restrictions` |

Reference data (64 districts, upazilas, the institution list with EIIN) loads through `scripts/seed_reference.py` from versioned CSVs in `backend/seed/`. Migrations never contain bulk data. `alembic check` must report no drift between the models and the migrations.

### B.4 Transaction requirements

| Operation | Boundary |
|---|---|
| OTP verify, sign in or sign up | One transaction: consume `otp_challenges` (row lock), find or create `users` and default `privacy_settings`, create `device_sessions` and the first `refresh_tokens`, write a security `audit_log` row, write the `user.signed_in` outbox row |
| Social sign-in | Provider verification **outside** the transaction. Then one transaction as above with `external_identities`. A unique violation on `(provider, provider_subject)` means a concurrent first sign-in won; re-read and sign in to that user (01 §5.2 R16). |
| Refresh | `SELECT … FOR UPDATE` on the token row; insert the child token; mark the parent rotated. Reuse of a rotated token revokes the whole family (R15). |
| Guardian consent confirm | Consume the OTP, insert `guardian_consents`, update the user's consent state, audit row, all in one transaction |
| Admin writes (role grants, moderation, runtime config) | Change plus `audit_log` in the same transaction through `ops.audited()` |
| Job execution | The handler's writes plus the `processed_events` insert in one transaction. A duplicate delivery hits the PK and is a no-op. |
| Outbox relay | Read batch → write a Parquet object to S3 → in one transaction: enqueue one consumer job per consumer per ≤ 500 events (deterministic `relay_batch_id`, used as the job `dedupe_key`), `UPDATE outbox SET relayed_at`, and advance `relay_checkpoints`. S3 object names are deterministic (`date/hour/relay-<first_id>.parquet`), so a crash between upload and commit only overwrites the same object (at-least-once with idempotent object names). |

### B.5 Data-integrity requirements

- No plain-text phone, email or guardian phone anywhere (DB, logs, events). A test greps the DB dump of the test run for any `+8801…` pattern.
- OTP codes are stored as HMAC hashes. Comparison is constant-time.
- `audit_log` is append-only by privilege. A test asserts that `UPDATE` raises `insufficient_privilege` under `app_rw`.
- Every `role_grants` change produces an audit row (enforced by the service signature: grant functions require an `Audit` context).

---

## C. Backend implementation

### C.1 Implementation steps (exact order)

1. **Tooling skeleton:**
   - `pyproject.toml`, `uv.lock`, `.python-version` (3.13), `.gitignore`, `.env.example`, `docker-compose.yml`, `Dockerfile`, `.importlinter`, `.pre-commit-config.yaml`;
   - `scripts/check.sh`, `scripts/check_file_length.py`, `scripts/check_boundaries.py`, `scripts/check_coverage_paths.py`;
   - the CI workflow.
   - Commit when `scripts/check.sh` passes on an empty package with one smoke test.
2. **`core` basics:** `settings`, `logging`, `errors`, `clock`, `ids`, then `http` (`create_app`, health, middleware). Tests for health and errors.
3. **`core.db`:** async engine, sessionmaker, naming convention, `Base`, and the test fixtures for rolled-back transactions and template databases. Add `migrations/env.py` and `b01_01`. Write `modules/registry.py` with a test that registry schemas equal the migration list.
4. **`core.redis`, `core.ratelimit`, `core.resilience`** (circuit breaker, retry with jitter), **`core.storage`** (S3 presign through localstack), **`core.security`**:
   - JWT EdDSA sign and verify;
   - `crypto.py` envelope encryption with a KMS adapter (a local key file in dev and test);
   - `keyed_hash`.
5. **Platform module (NFR):**
   - migrations `b01_02`–`b01_04`;
   - jobs runtime (`enqueue`, `claim`, `run_worker`, retries, dead jobs);
   - outbox `publish`;
   - relay job to S3 Parquet;
   - `processed_events` consumer wrapper;
   - idempotency dependency;
   - runtime_config with a Redis cache;
   - the partition maintenance job.
6. **OPS audit:** migration `b01_05`; the `audited()` context manager; the audit search route; and the runtime-config admin route, which uses `audited`.
7. **Entry points:** `api`, `workers`, `ai_gateway`, `exam_ingest`, `exam_consumers`, each booting with `/livez` and `/readyz` (the HTTP ones) or `--check` (the workers). Add the exam-ingest isolation subprocess test now.
8. **PLAN SMS:** migration `b01_11`; the `SmsGateway` protocol; the fake adapter and the HTTP adapter (vendor chosen later, behind settings); templates with Bangla numerals; the `notify.send_sms` public function (enqueues a high-priority job), plus a synchronous path for OTP that uses the job queue at priority 100.
9. **AUTH core:** migrations `b01_06`–`b01_10`; users; OTP send and verify with the abuse limits; tokens and refresh; device sessions; `current_actor` dependency; RBAC and `can()`; profiles and reference lists; privacy settings; guardian consent.
10. **AUTH social sign-in:**
    - the `SocialProvider` protocol;
    - the Google and Facebook adapters;
    - the nonce service;
    - the sign-in and linking service, with the pending sign-up token (DOB before creation, R-24);
    - step-up OTP and the dormant/new-device rules (R-25);
    - identities routes;
    - the Meta callbacks.

10a. **Staff SSO (R-07):**
    - the OIDC client (`core/security/oidc.py`);
    - `auth/internal/services/staff_sso.py`, which requires MFA `amr`, an allowed domain and an existing staff grant;
    - the routes `GET /v1/admin/auth/sso/start` and `GET /v1/admin/auth/sso/callback`;
    - the admin-audience dependency, which rejects any token without `sso=true`.

    This must exist before any admin route ships.
11. **COM moderation:** migration `b01_12`; normalisation and folding (shared with search in B2, through `shared/bangla_text.py`); `moderate()`; reports, restrictions and admin routes. Wire `moderate()` into display-name and profile updates.
12. **Seed and smoke:**
    - `scripts/seed_reference.py`;
    - `scripts/seed_dev.py`: one super admin, test users, and Facebook and Google test identities through fakes;
    - an end-to-end API test covering OTP sign-up → profile → consent → refresh → revoke.
13. **Hardening pass:** security headers, CORS allow-list, request size limits, log redaction tests, coverage thresholds, docs (`backend/README.md`).

### C.2 Folder structure changes

The `.gitkeep` files are replaced by real packages. New folders:
- `core/`
- `shared/`
- `modules/{nfr,ops,auth,com,plan}/{contracts,internal/{models,repositories,services,schemas,routes,events,jobs,providers}}`
- `entrypoints/{api,workers,ai_gateway,exam_ingest,exam_consumers}/`
- `migrations/helpers/`
- `seed/`
- `tests/{core,shared,entrypoints,contract,modules/{nfr,ops,auth,com,plan}}/`

The other 11 module folders get only `__init__.py` with `CODE` and `SCHEMA` constants (the registry test requires them) and an empty `internal/__init__.py`.

### C.3 Files to create

Line counts are estimates. Every handwritten file must be ≤ 200 lines; aim for 50–150.

**Repository root (`backend/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `pyproject.toml` | Project metadata, dependencies, tool configs (§C.9) | 150 |
| `.importlinter` | Layers and exam-ingest isolation contracts (§C.9) | 40 |
| `.pre-commit-config.yaml` | Hooks (§C.9) | 60 |
| `docker-compose.yml` | `postgres` (`pgvector/pgvector:pg17`), `pgbouncer` (profile `pool`), `redis:7`, `localstack` (sqs, s3, kms) | 70 |
| `Dockerfile` | Multi-stage: `uv` build, slim runtime, non-root user; `ARG WITH_NODE` for the worker image (used from B2) | 50 |
| `.env.example` | Every setting with safe local defaults | 60 |
| `alembic.ini` | `script_location`, `prepend_sys_path = src`, `file_template = %%(rev)s_%%(slug)s` | 30 |
| `README.md` | Run, test, layout, conventions summary | 120 |
| `.github/workflows/backend.yml` (repo root) | CI jobs (§C.9) | 140 |
| `scripts/check.sh` | `ruff format --check` → `ruff check` → `mypy` → `lint-imports` → `check_boundaries.py` → `check_file_length.py` → `pytest --cov` → `check_coverage_paths.py` | 30 |
| `scripts/check_file_length.py` | Fails if any tracked handwritten file under `src/`, `tests/`, `migrations/`, `scripts/` or `edge/` exceeds 200 physical lines. Reads `scripts/line_limit_exempt.txt` (exact paths, each with a reason comment). | 70 |
| `scripts/line_limit_exempt.txt` | Exemptions: `uv.lock`, `openapi.json` (generated) | 10 |
| `scripts/check_boundaries.py` | Uses `grimp` to build the import graph of `app`. Fails if any module imports `app.modules.<X>.internal` where it is not X, if any import cycle exists between module public packages, or if `internal` imports `fastapi` outside `routes/` and `schemas/`. | 120 |
| `scripts/check_coverage_paths.py` | Reads `coverage.json`; enforces 95% line and branch coverage per critical-path glob listed in `pyproject [tool.critical_coverage]` | 70 |
| `scripts/seed_reference.py` | Loads districts, upazilas and institutions from CSV with an upsert | 90 |
| `scripts/seed_dev.py` | Dev users, admin role grant, test identities | 80 |

**`src/app/core/`**

| Path | Responsibility | ~Lines |
|---|---|---|
| `core/settings.py` | pydantic-settings `Settings`: env, db and redis URLs, PgBouncer mode, JWT keys, KMS, S3, SQS, SMS, Google and Facebook config, CORS, rate limits. Validator refuses unsafe prod config (debug on, wildcard CORS, memory queue, fake SMS, missing social secrets when enabled, key under 32 bytes). `get_settings()` is cached. | 160 |
| `core/settings_parts.py` | Nested setting groups (`DbSettings`, `AuthSettings`, `SocialSettings`, `StorageSettings`) to keep `settings.py` under 200 lines | 120 |
| `core/logging.py` | structlog configuration, JSON or console, PII redaction processor (phone, email, token, otp, answer_key keys) | 110 |
| `core/request_context.py` | Pure-ASGI middleware: validate or generate `X-Request-ID`, bind contextvars, one access log line, trace id propagation | 90 |
| `core/errors.py` | `AppError` hierarchy (starter, extended with `ForbiddenError`, `ValidationAppError`, `LockedError`, `UnavailableError`, `GoneError`, `UpgradeRequiredError`) and handlers producing the 14 §1.5 envelope | 120 |
| `core/http.py` | `create_app(service, routers, ready_checks)`: middleware order, CORS, security headers, GZip/Brotli, docs only outside prod, `/livez`, `/readyz` with 2 s checks, `X-Min-App-Version` header | 140 |
| `core/clock.py` | `Clock` protocol, `SystemClock`, `FrozenClock` (tests), `get_clock` dependency | 50 |
| `core/ids.py` | `uuid7()` (stdlib `uuid.uuid7` on 3.14; a vendored implementation on 3.13) | 50 |
| `core/db.py` | Async engine (asyncpg) with `connect_args={"statement_cache_size": 0}` when `DB_POOL_MODE=pgbouncer`, pool sizes, `statement_timeout` and `lock_timeout` via `server_settings`, sessionmaker, `get_session` dependency, `ping_db` | 110 |
| `core/db_base.py` | `Base` with a metadata naming convention; common column helpers (`uuid_pk`, `created_at`, `updated_at`, `CheckIn`) | 80 |
| `core/redis.py` | Async Redis client, `ping_redis`, typed get/set JSON helpers | 60 |
| `core/ratelimit.py` | Sliding-window limiter (Lua script) by key; `rate_limit(tier, key_fn)` FastAPI dependency; tiers loaded from settings and runtime_config | 140 |
| `core/resilience.py` | `CircuitBreaker` (Redis-backed state, 50% errors over 30 s, half-open probe), `retry_async` with exponential backoff and jitter | 130 |
| `core/storage.py` | S3 client (aioboto3), `presign_put(purpose, key, content_type, max_bytes)`, `presign_get`, key naming per purpose | 110 |
| `core/security/jwt.py` | EdDSA (Ed25519) sign and verify with `kid` rotation; access, admin and exam token types; claims validation | 140 |
| `core/security/crypto.py` | Envelope encryption: AES-256-GCM with a data key wrapped by KMS; `encrypt_field`, `decrypt_field`; key ids stored in the ciphertext header | 120 |
| `core/security/hashing.py` | `keyed_hash(value, purpose)` HMAC-SHA256; constant-time compare; OTP hash | 50 |
| `core/security/kms.py` | `KmsClient` protocol with an AWS KMS adapter and a local-file adapter | 80 |
| `core/http_client.py` | Shared HTTPX `AsyncClient` factory with timeouts, user agent and OTel instrumentation | 50 |
| `core/telemetry.py` | OpenTelemetry tracer and meter setup; metric helpers | 90 |

**`src/app/shared/`**

| Path | Responsibility | ~Lines |
|---|---|---|
| `shared/types.py` | `Poisha` (NewType int), `BdPhone`, `Lang` literal, `DhakaDate` | 70 |
| `shared/poisha.py` | Format poisha as a display string (Bangla or English numerals, lakh grouping); parse provider decimal strings using `money.py` | 80 |
| `shared/money.py` | Starter copy (Decimal helpers), used only by payment adapters | 120 |
| `shared/bd_phone.py` | Starter copy: normalise and validate +88 numbers | 90 |
| `shared/dhaka_date.py` | Starter copy plus `dhaka_date(ts)`, `dhaka_week_key(date)` (Saturday start), `dhaka_month_key` | 110 |
| `shared/bangla_text.py` | NFC normalisation, zero-width removal, nukta forms, Bangla↔ASCII digits, phonetic folding (ি/ী, ু/ূ, ণ/ন, শ/ষ/স), basic romanisation folding for Banglish | 160 |
| `shared/numerals.py` | Bangla numeral formatting for templates | 40 |

**`src/app/modules/nfr/` (platform)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `nfr/__init__.py` | Public API: `publish`, `enqueue`, `job`, `consumer`, `idempotent`, `get_runtime_flag`, `routers()`, `job_handlers()` | 50 |
| `nfr/contracts/events.py` | `EventEnvelope` (v2 §3.3), `schema_version` registry | 70 |
| `nfr/contracts/jobs.py` | `JobHandler` protocol, `JobContext` | 40 |
| `core/jobs/queues.py` | `QUEUES` tuple, the single canonical queue list (R-04), and `Priority` bounds (−100..100). It has no imports beyond the standard library, so migrations can import it. | 25 |
| `nfr/internal/models/queue.py` | `Job`, `DeadJob`, `ProcessedEvent` | 90 |
| `nfr/internal/models/outbox.py` | `OutboxEvent`, `RelayCheckpoint` | 60 |
| `nfr/internal/models/config.py` | `RuntimeConfig`, `IdempotencyKey` | 60 |
| `nfr/internal/repositories/jobs.py` | `insert_job` (`ON CONFLICT (dedupe_key) DO NOTHING`), `claim_jobs(queue, n, lease)` (SKIP LOCKED CTE on `status='queued'`), `complete` (delete if unkeyed, else `status='done'` until `dedupe_until`), `fail_or_retry`, `move_to_dead`, `purge_expired_dedupe` | 150 |
| `nfr/internal/repositories/outbox.py` | `insert_event`, `fetch_unrelayed(batch)`, `mark_relayed(ids)` | 80 |
| `nfr/internal/repositories/idempotency.py` | `get`, `insert_pending`, `store_response` | 70 |
| `nfr/internal/services/publish.py` | `publish(session, envelope)`: validation and insert | 50 |
| `nfr/internal/services/enqueue.py` | `enqueue(session, kind, payload, queue, run_at, priority, dedupe_key, dedupe_until)`; rejects a queue not in `QUEUES` | 60 |
| `nfr/internal/services/runner.py` | Worker loop: claim → dispatch → commit; lease renewal; graceful shutdown; metrics | 160 |
| `nfr/internal/services/consumer.py` | `@consumer(name, event_type, batched=True)` decorator: the handler receives up to 500 events; the wrapper inserts one `processed_events (consumer, relay_batch_id)` row in the same transaction (single-event consumers use the event id) | 80 |
| `nfr/internal/services/idempotency.py` | `idempotent(route_id)` dependency: request hash, replay, 422 on mismatch, in-flight lock with `SETNX` | 140 |
| `nfr/internal/services/runtime_config.py` | Get and set flags with a 30 s Redis cache; `require_enabled(key)` raises `UnavailableError(kill_switch)` | 90 |
| `nfr/internal/jobs/relay.py` | `platform.outbox.relay`: batch of 1,000 → event-type routing into **one consumer job per consumer per batch of up to 500 events** (never one job per event; 17 §2 job-queue finding) → Parquet to S3 | 150 |
| `nfr/internal/jobs/parquet_writer.py` | pyarrow schema per envelope; deterministic object keys | 90 |
| `nfr/internal/jobs/partition_maintenance.py` | Declarative partition list (01 §1.2); create ahead and drop expired (only tables flagged droppable) | 130 |
| `nfr/internal/jobs/retention.py` | Batched deletes for `idempotency_keys`, `otp_challenges`, `dead_jobs` | 80 |
| `nfr/internal/routes/config.py` | `GET /v1/config/client`, `GET /v1/uploads/{purpose}/presign` | 90 |
| `nfr/internal/schemas/config.py` | Client config and presign schemas | 60 |

**`src/app/modules/ops/`**

| Path | Responsibility | ~Lines |
|---|---|---|
| `ops/__init__.py` | Public: `audited`, `AuditTarget`, `routers()` | 30 |
| `ops/internal/models/audit.py` | `AuditLog` (partitioned) | 50 |
| `ops/internal/repositories/audit.py` | `insert`, `search(filters, cursor)` | 80 |
| `ops/internal/services/audited.py` | `audited(session, actor, action, target, reason, before)` async context manager; diff of changed fields; PII redaction | 110 |
| `ops/internal/routes/admin_audit.py` | `GET /v1/admin/audit-log`, `PUT /v1/admin/runtime-config/{key}` | 90 |
| `ops/internal/schemas/audit.py` | Schemas | 60 |

**`src/app/modules/auth/`**

| Path | Responsibility | ~Lines |
|---|---|---|
| `auth/__init__.py` | Public: `current_actor`, `Actor`, `require`, `can`, `get_user_summary`, `get_profile`, `is_minor`, `routers()`, `job_handlers()` | 60 |
| `auth/contracts/actor.py` | `Actor`, `UserSummary`, `ProfileDTO` | 70 |
| `auth/internal/models/user.py` | `User`, `ExternalIdentity` | 90 |
| `auth/internal/models/session.py` | `OtpChallenge`, `DeviceSession`, `RefreshToken` | 100 |
| `auth/internal/models/rbac.py` | `Role`, `Permission`, `RolePermission`, `RoleGrant` | 80 |
| `auth/internal/models/profile.py` | `Profile`, `District`, `Upazila`, `Institution` | 100 |
| `auth/internal/models/consent.py` | `ConsentDocument`, `GuardianConsent`, `PrivacySetting` | 80 |
| `auth/internal/repositories/users.py` | Find by phone hash, email hash, id; create; update | 110 |
| `auth/internal/repositories/identities.py` | Find by `(provider, subject)`; list active for user; link and unlink | 90 |
| `auth/internal/repositories/otp.py` | Create, latest for phone, lock and consume, count recent | 80 |
| `auth/internal/repositories/sessions.py` | Create session; list; revoke; tokens insert, lock, rotate, revoke family | 130 |
| `auth/internal/repositories/rbac.py` | Grants for user (cached), insert and revoke grant | 80 |
| `auth/internal/repositories/profiles.py` | Profile get and upsert; reference search (trigram) | 100 |
| `auth/internal/repositories/consent.py` | Consent insert, current consent, privacy get and upsert | 70 |
| `auth/internal/services/otp_send.py` | Normalise phone; abuse limits (3 per 15 min, 5 per day per phone; IP and device limits); challenge flag; create challenge; `notify.send_sms` | 130 |
| `auth/internal/services/otp_verify.py` | Lock challenge, attempts ≤ 5, expiry, constant-time compare; consume; hand off to `sign_in` | 100 |
| `auth/internal/services/sign_in.py` | Shared: find or create user, apply restrictions (banned → 403), create session and tokens, audit, outbox `user.signed_in` | 140 |
| `auth/internal/services/tokens.py` | Issue access and refresh tokens; rotation with reuse detection; revocation cache in Redis | 140 |
| `auth/internal/services/sessions.py` | List and revoke sessions; logout | 70 |
| `auth/internal/services/social_nonce.py` | Issue a single-use nonce (`nonce:social:{nonce}` in Redis, 5 min); consume atomically (`GETDEL`) | 50 |
| `auth/internal/services/social_sign_in.py` | Verify via provider → identity lookup → the linking rules (C.5) → age gate → `sign_in` | 160 |
| `auth/internal/services/social_link.py` | Link from a signed-in session; unlink with the step-up OTP, verified-phone and last-method guards; conflict 409 | 130 |
| `auth/internal/services/pending_signup.py` | Pending sign-up token (Redis, 15 min, single use); `complete_sign_up(token, dob)`; the age gate before creation | 110 |
| `auth/internal/services/step_up.py` | Step-up OTP issue and verify (`purpose=step_up`); dormant/new-device rule; restricted-mode flag | 120 |
| `auth/internal/services/staff_sso.py` | OIDC start and callback; checks MFA `amr`, allowed domain and existing staff grant; issues `aud=admin` tokens with `sso=true`, 12 h refresh | 140 |
| `auth/internal/routes/staff_sso.py` | `/v1/admin/auth/sso/start`, `/v1/admin/auth/sso/callback` | 60 |
| `core/security/oidc.py` | Generic OIDC client: discovery, PKCE, state and nonce, JWKS verification (shared JWKS cache) | 130 |
| `auth/internal/services/meta_callbacks.py` | Verify `signed_request` (HMAC-SHA256 with the app secret, base64url, `algorithm == HMAC-SHA256`); data deletion → create an `identity.data_requests` row (`kind=deletion`, `requested_via=facebook`) with a confirmation code, and unlink the identity; deauthorise → unlink. The status endpoint reads the row. Executing the deletion stays support-driven until B6. | 140 |
| `auth/internal/services/rbac.py` | `can(actor, action, resource_scope)`, `require`, grant and revoke (audited) | 130 |
| `auth/internal/services/profile.py` | Profile update with validation (class ↔ group, board, exam year), photo confirm (moderation hook, `photo_status`), display-name moderation | 140 |
| `auth/internal/services/consent.py` | Age computation (Dhaka date), guardian OTP start and confirm, consent record, privacy defaults for minors | 140 |
| `auth/internal/services/actor.py` | `current_actor` dependency: verify JWT, check the revocation cache, load grants (Redis cache 60 s), suspended check | 110 |
| `auth/internal/providers/base.py` | `SocialProvider` protocol, `VerifiedIdentity` dataclass, `ProviderError` | 50 |
| `auth/internal/providers/jwks.py` | JWKS fetch with an HTTPX client, cache by `kid` in Redis honouring `Cache-Control`, refetch once on an unknown `kid` | 100 |
| `auth/internal/providers/google.py` | ID token verification: RS256 signature against Google JWKS, `iss` ∈ {`accounts.google.com`, `https://accounts.google.com`}, `aud` ∈ configured client ids, `exp`, `iat` skew ≤ 60 s, `nonce` equals the issued nonce; returns subject, email, `email_verified`, name | 110 |
| `auth/internal/providers/facebook.py` | `GET /debug_token?input_token=…&access_token={app_id}|{app_secret}` → check `data.is_valid`, `data.app_id == settings`, `data.user_id`, `expires_at`; then `GET /me?fields=id,name,email` with `appsecret_proof`; iOS Limited Login OIDC token path (JWKS `https://limited.facebook.com/.well-known/oauth/openid/jwks/`, `aud = app_id`, nonce) | 150 |
| `auth/internal/providers/registry.py` | Provider name → instance from settings; disabled providers return 404 | 40 |
| `auth/internal/routes/auth_otp.py` | `/v1/auth/otp/send`, `/v1/auth/otp/verify` | 80 |
| `auth/internal/routes/auth_social.py` | `/v1/auth/social/nonce`, `/v1/auth/social/{provider}` | 70 |
| `auth/internal/routes/auth_tokens.py` | `/v1/auth/refresh`, `/v1/auth/logout` | 60 |
| `auth/internal/routes/me.py` | `/v1/me` GET and PATCH, sessions, identities, phone | 140 |
| `auth/internal/routes/profile.py` | Profile, photo, privacy, consent routes | 140 |
| `auth/internal/routes/reference.py` | Districts, institutions, consent documents | 70 |
| `auth/internal/routes/meta_webhooks.py` | Facebook data deletion, deletion status, deauthorise | 80 |
| `auth/internal/routes/admin_roles.py` | Role grants create and revoke | 60 |
| `auth/internal/schemas/*.py` (4 files: `auth.py`, `me.py`, `profile.py`, `admin.py`) | Request and response models | 4 × 90 |
| `auth/internal/jobs/cleanup.py` | Expire nonces (Redis TTL) — no-op; purge stale sessions after 90 days without activity (marks revoked) | 50 |
| `auth/internal/permissions.py` | Permission code constants and seed list (used by the migration seed and `can`) | 90 |

**`src/app/modules/plan/` (SMS only in B1)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `plan/__init__.py` | Public: `send_sms(session, to_phone, template_code, params, purpose, priority)` | 30 |
| `plan/internal/models/sms.py` | `SmsMessage`, `Template` | 70 |
| `plan/internal/repositories/sms.py` | Insert, update status | 60 |
| `plan/internal/services/templates.py` | Render a template (lang, Bangla numerals); segment count (GSM-7 160 / UCS-2 70, concatenated 153 / 67) | 100 |
| `plan/internal/providers/sms_base.py` | `SmsGateway` protocol | 30 |
| `plan/internal/providers/sms_fake.py` | Fake gateway (records; exposes the last code to tests) | 40 |
| `plan/internal/providers/sms_http.py` | Generic HTTP gateway adapter (vendor config by settings) with the circuit breaker | 100 |
| `plan/internal/jobs/sms_send.py` | `plan.sms.send` job: render → gateway → status and cost | 90 |

**`src/app/modules/com/`**

| Path | Responsibility | ~Lines |
|---|---|---|
| `com/__init__.py` | Public: `moderate(session, text, context, target_ref) -> ModerationVerdict`, `is_restricted(user_id, scope)` | 30 |
| `com/contracts/moderation.py` | `ModerationVerdict` (allow, flag, block; terms; score) | 30 |
| `com/internal/models/moderation.py` | `ModerationTerm`, `ModerationDecision`, `ContentReport`, `UserRestriction` | 100 |
| `com/internal/repositories/*.py` (`terms.py`, `reports.py`, `restrictions.py`) | Queries; terms loaded into a process cache (refreshed every 5 min) | 3 × 70 |
| `com/internal/services/moderate.py` | Normalise with `shared.bangla_text` → token and n-gram match against folded terms → verdict by severity; log decisions for `flag` and `block` | 120 |
| `com/internal/services/reports.py` | Create a report; resolve (audited) | 80 |
| `com/internal/services/restrictions.py` | Mute and ban (audited); `is_restricted` cached 60 s | 90 |
| `com/internal/routes/reports.py`, `com/internal/routes/admin_moderation.py` | Routes | 60 + 140 |
| `com/internal/schemas/moderation.py` | Schemas | 80 |
| `seed/moderation_terms.csv` | Initial term list (content team supplies) | data |

**Entry points**

| Path | Responsibility | ~Lines |
|---|---|---|
| `entrypoints/api/main.py` | `create_app("api", routers=[…all module routers()], ready_checks={db, redis})` | 50 |
| `entrypoints/workers/main.py` | Registers every module's `job_handlers()`; `run_worker(queues)`; `--check` | 60 |
| `entrypoints/ai_gateway/main.py` | `create_app("ai-gateway", routers=[], ready_checks={db, redis})` (routers arrive in B4) | 30 |
| `entrypoints/exam_ingest/main.py` | `create_app("exam-ingest", routers=[], ready_checks={redis})`; must not import `core.db` | 30 |
| `entrypoints/exam_consumers/main.py` | Consumer process skeleton; `--check` validates the SQS settings | 50 |

**Tests (B1):** see §E for files.

### C.4 Business rules and validation

| Area | Rule |
|---|---|
| Phone | Accept `01XXXXXXXXX`, `+8801XXXXXXXXX` or `8801…`; normalise to E.164 `+8801[3-9]XXXXXXXX`; otherwise 422 `invalid_phone` |
| OTP | 6 digits, 5 min expiry, 5 attempts; **T-otp** limits (3 per phone per 15 min, 5 per day, 10 per IP per hour); after 3 failures across challenges within 1 h on a phone, require a CAPTCHA token (`challenge_required` 403 with a `challenge_url`) |
| Test phones (R-31) | Reserved block `+8801700000000`–`+8801700009999`, which matches the phone regex. The SMS adapter never sends to it, and a fixed OTP from settings is accepted. It is allowed only when `APP_ENV` is `test` or `dev`; the prod and staging settings validator refuses a non-empty test-OTP setting. |
| Request body (R-32) | 256 KB maximum for JSON bodies by default; 1 MB for the batch endpoints (`/v1/practice/answers:sync`, `/v1/events:batch`, exam ingest). Larger bodies get 413 `payload_too_large`. |
| Sign-up needs DOB (R-24) | No `users` row is created, by any method (OTP, Google, Facebook), until `date_of_birth` is supplied. A first sign-in without a DOB returns 200 `{status: "needs_profile", pending_signup_token, required: ["date_of_birth"]}`. The pending token is single use, valid 15 min, bound to the verified phone or provider identity, and kept in Redis under `auth:pending_signup:{token}`. `POST /v1/auth/sign-up/complete {pending_signup_token, date_of_birth, display_name?}` creates the user. The age gate runs before creation, so an under-13 Facebook attempt is rejected (403 `age_restricted`) with nothing created. |
| Step-up OTP (R-25) | Unlinking an identity, changing the phone, requesting deletion and changing the guardian phone each need a fresh OTP to the account's verified phone (`purpose = step_up`, valid 10 min), carried as `X-Step-Up-Token`. Unlinking a social identity also needs a verified phone on the account. |
| Dormant and SIM-swap rules (R-25) | No sign-in for 180 days and a new `device_id` → after the OTP, a second factor is also required where one exists (a linked Google or Facebook identity); otherwise the session starts in restricted mode (no phone change, no unlink, no payments) for 72 h. Recovery or a phone change from a new device needs a second linked method or a support check (number recycling by operators). A guardian phone change re-runs guardian consent with OTPs to both the old and the new guardian numbers, or a support check. |
| Session | One device session per (user, device_id), reused on re-sign-in; access 15 min; refresh 30 days sliding; staff refresh 12 h; max 10 active sessions per user (oldest revoked) |
| Refresh reuse | Presenting a rotated or revoked refresh token revokes every token in `family_id` and the session; audit `auth.refresh_reuse` |
| Display name | 2–40 characters, letters and spaces in Bangla or Latin script; `moderate(context='display_name')` must not block |
| Profile | `class_level` 6–12 or `admission`/`job`; `group_code` required for classes 9–12 (science, business, humanities); `version_lang` bn or en; `curriculum` general, madrasah or technical; `exam_year` between the current year and the current year + 6; institution must exist and be active |
| Age | `date_of_birth` required **before account creation** (see above); age computed on the Dhaka date; under 18 → `needs_consent = true` until guardian consent; under 13 → Facebook sign-in and Facebook linking refused (403 `age_restricted`). A Facebook-only account can no longer exist without a DOB, so the "unlink later" case cannot arise. |
| Guardian consent | Guardian phone must differ from the user's phone; OTP purpose `guardian_consent`; consent version must be the latest published `consent_documents.version` |
| Privacy defaults | `profile_private = true`; `leaderboard_visible = true` (NFR-07 and v2 C13: first name and institution only) with self or guardian opt-out |

### C.5 Social sign-in design (approved plan)

```
POST /v1/auth/social/nonce        → {nonce, expires_at}          (Redis nonce:social:{nonce}, 5 min, single use)
client: native/web SDK obtains provider token with that nonce (Google ID token; Facebook access token or Limited Login OIDC)
POST /v1/auth/social/{provider}   {token, nonce, device, date_of_birth?}
  1. registry.get(provider) → 404 if disabled
  2. consume nonce (GETDEL); missing → 401 invalid_nonce
  3. provider.verify(token, nonce) → VerifiedIdentity(subject, email, email_verified, name)   [timeout 3 s, circuit breaker]
  4. identity exists (provider, subject)        → sign in to its user (blocked if user banned or deleted)
  5. else Google with email_verified AND an existing user with verified email_hash match → link and sign in (audit auth.identity_autolinked)
  6. else (new account): if no date_of_birth → 200 {status: needs_profile, pending_signup_token}; nothing is created (R-24)
  7. age gate before creation: age < 13 and provider == facebook → 403 age_restricted, nothing created
  8. create the user (needs_consent per age) + external_identities row, in one transaction
  9. Facebook: never auto-link by email (step 5 skipped); email stored only as an unverified attribute
 10. sign_in(): device session + tokens + audit + outbox user.signed_in {method}; dormant/new-device rule (C.4)
```

**Linking from a session:** `POST /v1/me/identities/{provider}` with `{token, nonce}`.
- If the identity is already linked to another user, return 409 `identity_in_use`.
- If the user already has an active identity for that provider, return 409 `conflict`.

**Unlinking:**
- Requires a step-up OTP and a verified phone on the account (403 `phone_required` otherwise).
- Count the active sign-in methods (verified phone plus active identities, and password from B8). Refuse with 409 `last_sign_in_method` if only one remains.

**Meta data deletion:**
- Verify `signed_request`: split on `.`, base64url-decode the signature, and compare it with HMAC-SHA256(payload, app_secret) using constant time; require `algorithm = HMAC-SHA256`.
- Find the identity for `user_id` and unlink it.
- Record a confirmation code and queue a support data request. Until B6 this is the audit log plus a `facebook_deletion` key in runtime-config style storage; B6 moves it to `identity.data_requests`.
- Return `{"url": "https://<host>/v1/auth/social/facebook/deletion-status/{code}", "confirmation_code": code}`.

**Deauthorise:** verify `signed_request` the same way, unlink the identity and audit it.

**Provider outage:** the circuit breaker opens and returns 503 `unavailable` with `details.fallback = "phone_otp"`.

### C.6 Roles and permissions (seed)

Roles: `student`, `parent`, `teacher`, `institution_admin`, `content_author`, `reviewer`, `ops_admin`, `super_admin`.

Permission codes created in B1 (later builds add theirs through their own migrations): `user.read`, `user.write`, `role.grant`, `audit.read`, `ops.config`, `moderation`, `privacy`, `content.read`, `content.author`, `content.verify`, `content.publish`, `content.triage`, `content.lead`, `content.exam`, `curriculum`.

`can(actor, action, scope)` returns true when the actor has a grant with the permission and either `scope_type='global'` or a scope that covers the resource:
- a `subject` grant covers its descendants (checked through TAX from B2 via `tax.is_descendant`);
- a `tenant` grant equals the resource tenant.

`super_admin` bypasses checks, but every bypass is audited.

### C.7 Jobs and workers

| Job kind | Queue | Trigger | Idempotency |
|---|---|---|---|
Queue names come only from `core/jobs/queues.py`: `default, relay, notify, sms, gam, rescoring, imports, ai, exam, campaign, payments, maintenance`. The `platform.jobs.queue` CHECK is generated from that tuple, and `tests/contract/test_job_queues.py` asserts that the two are equal (R-04). Priority is −100..100.

| Job kind | Queue | Trigger | Idempotency |
|---|---|---|---|
| `platform.outbox.relay` | `relay` | A dedicated loop: polls every **250 ms while there is work and every 1 s when idle**, over a direct (non-PgBouncer) connection (R-17). Each batch of up to 1,000 events becomes **one consumer job per consumer per ≤ 500 events**, with a deterministic `relay_batch_id = first_event_id:last_event_id`. | Deterministic object keys; `relayed_at`; consumer jobs dedupe on `(consumer, relay_batch_id)` |
| `platform.partition.maintain` | `maintenance` | Daily at 02:00 Dhaka (`dedupe_key = partitions:{date}`, `dedupe_until` = next day) | Create `IF NOT EXISTS`; drop by name |
| `platform.retention.purge` | `maintenance` | Hourly; also deletes keyed `done` jobs whose `dedupe_until` has passed | Batched deletes |
| `plan.sms.send` | `sms` (priority 100 for OTP) | Enqueued by `send_sms` | `processed_events(consumer, sms_id)` |
| `auth.sessions.purge_stale` | `maintenance` | Daily | Pure update |

**Job lifecycle (R-18).** `status` goes `queued → running → done | failed`:
- A job **without** a `dedupe_key` is deleted on completion.
- A job **with** one is kept as `done` until `dedupe_until`, so a scheduler cannot re-enqueue it inside its window.
- Failed jobs move to `dead_jobs`.

The worker runs with `--queues sms,maintenance,default` in B1; later builds add queues per worker service. The relay runs as its own loop (above). Workers poll every 200 ms when there is work, with a 1 s backoff when idle. There is a lease of 60 s, renewed every 20 s. Up to 8 attempts are made with backoff `2^n × 5 s ± 20%`; after that the job moves to `dead_jobs` and `app_jobs_dead_total` is incremented (an alert rule in [`19`](19_devops_and_deployment.md)).

### C.8 Caching (Redis keys from 01 §3.17)

`rl:*`, `otp:send:{phone_hash}`, `nonce:social:{nonce}`, `jwks:{provider}`, `revoked_sess:{session_id}`, `cfg:runtime`. Also used: `auth:grants:{user_id}`, which holds the actor grants, has a 60 s TTL and is invalidated on a grant change. **Proposed addition** (below).

### C.9 Tool configuration (exact intent)

**`pyproject.toml`:**
- `[project]`: `requires-python = ">=3.13,<3.14"`.
- Dependencies: `fastapi`, `uvicorn[standard]`, `pydantic`, `pydantic-settings`, `sqlalchemy[asyncio]>=2.0.36`, `asyncpg`, `alembic`, `redis`, `structlog`, `httpx`, `pyjwt[crypto]`, `cryptography`, `aioboto3`, `pyarrow`, `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `uuid-utils` (if the vendored uuid7 is not used).
- Dev group: `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-xdist`, `httpx`, `respx` (optional; HTTPX `MockTransport` is preferred), `mypy`, `ruff`, `import-linter`, `grimp`, `pre-commit`, `pip-audit`, `freezegun` (no; use `FrozenClock`), `factory-boy` (no; use plain factory functions).
- Pin exact versions in `uv.lock`.

**`[tool.ruff]`:**
- `target-version = "py313"`, `line-length = 100`, `src = ["src", "tests"]`.
- `lint.select = ["E","W","F","I","B","C4","UP","S","ASYNC","N","SIM","RUF","PT","T20","ARG"]`, `ignore = ["E501"]`.
- `isort.known-first-party = ["app"]`.
- Per-file ignores: `tests/** = ["S101","S105","S106","S107","S311","ARG001"]` and `migrations/** = ["N999"]`.
- `format.quote-style = "double"`.

**`[tool.mypy]`:** `strict = true`, `python_version = "3.13"`, `plugins = ["pydantic.mypy"]`, `mypy_path = "src"`, `explicit_package_bases = true`, `warn_unreachable = true`, `disallow_any_generics = true`; overrides for untyped third-party packages (`aioboto3.*`, `pyarrow.*`) with `ignore_missing_imports = true` only.

**`[tool.pytest.ini_options]`:**
- `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`.
- `addopts = "-q --strict-markers -p no:cacheprovider"`, `filterwarnings = ["error"]`.
- Markers: `unit`, `integration`, `api`, `db`, `concurrency`, `contract`, `slow`, `eval`, `load`.

**`[tool.coverage.run]`** `branch = true`, `source = ["app"]`, `omit = ["*/entrypoints/*/main.py"]`.
**`[tool.coverage.report]`** `fail_under = 85`, `skip_covered = true`, `show_missing = true`.
**`[tool.critical_coverage]`** `paths = ["app/core/security/*", "app/core/ratelimit.py", "app/modules/nfr/internal/services/idempotency.py", "app/modules/nfr/internal/services/runner.py", "app/modules/nfr/internal/services/consumer.py", "app/modules/auth/internal/services/*", "app/modules/auth/internal/providers/*", "app/modules/ops/internal/services/audited.py"]`, `threshold = 95`.

**`.importlinter`:**
```ini
[importlinter]
root_package = app
include_external_packages = True

[importlinter:contract:layers]
name = Layers
type = layers
layers =
    app.entrypoints
    app.modules
    app.core
    app.shared

[importlinter:contract:ingest-no-postgres]
name = Exam ingest never touches Postgres
type = forbidden
source_modules =
    app.entrypoints.exam_ingest
    app.modules.exam.ingest
forbidden_modules =
    app.core.db
    sqlalchemy
    asyncpg
    alembic
```
`app.modules.exam.ingest` is a **public subpackage** of the EXAM module (`modules/exam/ingest/`, not under `internal/`), so the `exam_ingest` entry point imports it without breaking the layering or internal-privacy rules (R-26). It is created in B5; until then the contract lists only the entry point. The coverage globs in [`15`](15_testing_and_quality_standards.md) §5 and the B5 file paths in [`09`](09_build_05.md) §C use the same path.

**`.pre-commit-config.yaml`:**
- `pre-commit-hooks`: `check-yaml`, `check-toml`, `end-of-file-fixer`, `trailing-whitespace`, `check-added-large-files --maxkb=500`, `detect-private-key`, `check-merge-conflict`.
- `ruff-pre-commit`: `ruff --fix` and `ruff-format`.
- Local hooks: `mypy` (`uv run mypy src tests migrations`, `pass_filenames: false`), `line-limit` (`uv run python scripts/check_file_length.py`), `boundaries` (`uv run lint-imports && uv run python scripts/check_boundaries.py`).
- `gitleaks`.

**CI (`.github/workflows/backend.yml`).** Each job runs on `ubuntu-latest` with uv caching.
1. `lint`: ruff format check, ruff check, mypy, import-linter, boundaries, line limit.
2. `test`: services `pgvector/pgvector:pg17` and `redis:7`; `alembic upgrade head`, `alembic check`, then `pytest -m "not load and not eval" -n auto --cov --cov-report=xml --cov-report=json`; coverage gates.
3. `migrations`: upgrade head → downgrade to the previous revision → upgrade head again (every migration must be reversible or explicitly marked irreversible with a reason).
4. `security`: `pip-audit --strict`, `gitleaks detect`, `trivy fs` on the Dockerfile and lockfile.
5. `image`: build the Docker image (no push on PRs).

Required checks for merge: all five.

### C.10 Middleware order (outermost first)

1. `RequestContextMiddleware` (request id, trace id, access log)
2. `SecurityHeadersMiddleware` (`Strict-Transport-Security`, `X-Content-Type-Options`, `Referrer-Policy`, `Content-Security-Policy: default-src 'none'` for JSON)
3. CORS (allow-list from settings)
4. Body size limit: 256 KB JSON by default; 1 MB on the batch endpoints (`/v1/practice/answers:sync`, `/v1/events:batch`, exam ingest); uploads go directly to S3 (R-32)
5. GZip/Brotli
6. Routes. Rate limiting is a per-route dependency, not middleware, so tiers can differ by route.

### C.11 Error handling

Handlers live in `core.errors`: `AppError` subclasses map to their status and `code`. `RequestValidationError` becomes 422 `validation_error` with `details.fields`. Anything unhandled becomes 500 `internal_error` with only the request id exposed, logged with the stack trace. A `ProviderError` from social providers becomes 401 `invalid_provider_token` (invalid token) or 503 `unavailable` (provider down).

### C.12 Security requirements (B1 scope)

- Ed25519 signing keys for JWT come from the secret store.
  - Two active `kid`s are allowed during rotation.
  - Access tokens are never accepted after `revoked_sess` is set.
- No secrets in the repository. `.env.example` holds placeholders only, and gitleaks runs in pre-commit and CI.
- PII:
  - envelope-encrypt `phone_enc`, `email_enc` and `guardian_phone_enc`;
  - store `*_hash` with HMAC keys distinct per purpose (`phone`, `email`, `ip`, `device`);
  - IP addresses are stored only as `ip_hash`.
- Social: never log provider tokens; store no provider access token; use `appsecret_proof` for the Graph API.
- **Staff SSO with enforced 2FA is built in B1 (R-07).** The content team (B2) and the control room (B5) depend on it.
  - **OIDC client:** a generic OIDC client, Google Workspace by default (`STAFF_OIDC_ISSUER`, `STAFF_OIDC_CLIENT_ID`, `STAFF_OIDC_CLIENT_SECRET`, `STAFF_OIDC_ALLOWED_DOMAINS`). It uses the authorisation code flow with PKCE, `state` and `nonce`.
  - **Admin token issuance:** an `aud=admin` access token is issued only from the SSO callback, and only when the ID token's `amr` contains an MFA method (`mfa`, `otp`, `hwk` or `swk`) and the email domain is allowed; otherwise 403 `mfa_required`.
  - **Staff accounts:** a staff user must already exist with a staff role grant, and the SSO email hash must match.
  - **Lifetimes and dev mode:** staff refresh tokens last 12 h. Admin JWTs carry `sso=true` and `amr`, and admin routes reject any token without them.
  - **No local admin in prod:** break-glass local admin is disabled in prod, staging and the settings validator. `scripts/seed_dev.py` mints local staff tokens only when `APP_ENV` is `dev` or `test`.

### C.13 Configuration (env vars added)

| Group | Variables |
|---|---|
| App | `APP_ENV` (local, test, staging, prod), `LOG_LEVEL`, `LOG_JSON`, `CORS_ORIGINS`, `MIN_APP_VERSION` |
| Database | `DATABASE_URL` (`postgresql+asyncpg://…`), `DATABASE_MIGRATOR_URL`, `DB_POOL_MODE` (direct, pgbouncer), `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_STATEMENT_TIMEOUT_MS` |
| Redis | `REDIS_URL` |
| Auth | `JWT_PRIVATE_KEYS` (JSON kid → PEM, from secrets), `JWT_ACTIVE_KID`, `OTP_HASH_KEY`, `PII_HASH_KEYS`, `KMS_KEY_ID`, `KMS_BACKEND` (aws, local) |
| Social | `GOOGLE_ENABLED`, `GOOGLE_CLIENT_IDS` (comma list: android, web, ios), `FACEBOOK_ENABLED`, `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_GRAPH_VERSION` (pinned, `v27.0`: the latest version, released 2026-11-04, no end date yet; checked 2026-11-27. Do not use `v21.0`, which Meta removes on 2027-01-21) |
| Staff SSO (R-07) | `STAFF_OIDC_ISSUER` (default Google Workspace), `STAFF_OIDC_CLIENT_ID`, `STAFF_OIDC_CLIENT_SECRET`, `STAFF_OIDC_ALLOWED_DOMAINS`, `STAFF_OIDC_REDIRECT_URIS`; the prod validator requires all of them and refuses `DEV_STAFF_TOKENS=true` |
| SMS | `SMS_BACKEND` (fake, http), `SMS_API_URL`, `SMS_API_KEY`, `SMS_SENDER_ID`, `TEST_PHONE_OTP` (only for `APP_ENV` test or dev, block `+8801700000000–9999`) |
| Storage | `S3_ENDPOINT_URL` (localstack), `S3_BUCKET_UPLOADS`, `S3_BUCKET_EVENTS`, `AWS_REGION` |
| Telemetry | `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_SERVICE_NAME` |

---

## D. API contracts

All endpoints follow [14 §1](14_api_contracts.md). The schemas below list fields as `name: type (constraints)`.

**`POST /v1/auth/otp/send`**
- Purpose: send a sign-in OTP.
- Auth: Public. Tier T-otp. Idempotency optional.
- Request: `{phone: str (BD phone), purpose: "sign_in" (default), device_id: str (8–64), challenge_token?: str}`
- Response 202: `{challenge_id: uuid, expires_at: datetime, resend_after_s: int}`
- Errors: 422 `invalid_phone`; 429 `too_many_requests` (`Retry-After`); 403 `challenge_required`; 403 `forbidden` (banned number).
- The response is identical whether the number exists or not.

**`POST /v1/auth/otp/verify`**
- Request: `{challenge_id: uuid, code: str (6 digits), device: DeviceInfo{device_id, platform: android|web|ios, app_version, model?}}`
- Response 200: `TokenPair` (14 §2), with `user.needs_profile` and `user.needs_consent`.
- Errors: 401 `invalid_code` (attempts left in details); 410 `expired`; 429 after 5 attempts; 403 `forbidden` (banned).
- Tier T-auth.

**`POST /v1/auth/social/nonce`**
- Request: `{provider: google|facebook}`
- Response 200: `{nonce: str (32 bytes base64url), expires_at}`
- Errors: 404 `not_found` (provider disabled).
- Tier T-auth.

**`POST /v1/auth/social/{provider}`**
- Request: `{token: str (≤ 8 KB), nonce: str, device: DeviceInfo, date_of_birth?: date}`
- Response 200: `TokenPair` plus `{linked: bool, created: bool}`; or, for a new account without a DOB, `{status: "needs_profile", pending_signup_token, required: ["date_of_birth"]}`. No user is created in that case (R-24). `POST /v1/auth/otp/verify` behaves the same way for new phone numbers.

**`POST /v1/auth/sign-up/complete`** (R-24)
- Request: `{pending_signup_token, date_of_birth: date, display_name?}`
- Response 201: `TokenPair`
- Errors: 410 `expired`; 403 `age_restricted` (under 13 via Facebook); 422 for an invalid DOB.
- Tier T-auth; single use.

**`POST /v1/auth/step-up`** (R-25)
- Request: `{action: "unlink"|"phone_change"|"deletion"|"guardian_change", otp_challenge_id, code}`
- Response 200: `{step_up_token, expires_at}`. The token is valid 10 min and sent as `X-Step-Up-Token`.
- Tier T-auth.

**`GET /v1/admin/auth/sso/start`** (R-07)
- Request: `?redirect_uri` (allow-listed).
- Response: 302 to the IdP with PKCE, state and nonce.
- Public; tier T-auth.

**`GET /v1/admin/auth/sso/callback`**
- Request: `?code&state`.
- Response 200: an admin `TokenPair` (`aud=admin`, `sso=true`, 12 h refresh).
- Errors: 403 `mfa_required` (no MFA in `amr`), 403 `forbidden` (domain not allowed or no staff grant), 400 for an invalid state.
- Public; tier T-auth; audited as `auth.staff_sign_in`.
- Errors: 401 `invalid_provider_token`; 401 `invalid_nonce`; 403 `age_restricted`; 403 `forbidden` (banned); 404 provider disabled; 503 `unavailable` (`details.fallback = phone_otp`).
- Tier T-auth. Idempotency optional.

**`POST /v1/auth/refresh`**
- Request: `{refresh_token: str}`
- Response 200: `TokenPair`
- Errors: 401 `token_expired`; 401 `unauthorized` (reuse detected, so the session is revoked).
- Tier T-auth.

**`POST /v1/auth/logout`**
- Response 204. Revokes the current session and sets `revoked_sess`. Auth: User.

**`GET /v1/me` → `UserSummary`** plus `{phone_masked, identities: [{provider, linked_at}], consent: {required, status}}`

**`PATCH /v1/me`**
- Request: `{display_name?: str (2–40), first_name?: str (1–30), locale?: bn|en}`
- Response: `UserSummary`
- Errors: 422 `validation_error`; 422 `moderation_blocked`.

**`GET /v1/me/sessions`** → `Page<{session_id, platform, app_version, model, created_at, last_seen_at, current: bool}>`

**`DELETE /v1/me/sessions/{session_id}`**: 204. Errors: 404 if the session is not the caller's.

**`GET /v1/me/identities`** → `{items: [{provider, display_name, email_masked, linked_at, last_login_at}], phone_verified: bool}`

**`POST /v1/me/identities/{provider}`**
- Request: `{token, nonce}`
- Response 201: identity item
- Errors: 409 `identity_in_use`; 409 `conflict`; 401 `invalid_provider_token`; 403 `age_restricted`.

**`DELETE /v1/me/identities/{provider}`**: 204. Errors: 409 `last_sign_in_method`; 404.

**`POST /v1/me/phone`**: two steps through `purpose=phone_change`.
- Request: `{phone}` returns a challenge; then `{challenge_id, code}` returns 200 `{phone_masked}`.
- Errors: 409 `conflict` (phone used by another account; manual support merge only).

**`GET /v1/me/profile`** and **`PUT /v1/me/profile`**
- Request: `{class_level, group_code?, version_lang, curriculum, institution_id?, district_id?, upazila_id?, board_code?, exam_year?, date_of_birth?}`
- Response: `ProfileDTO` plus `{needs_consent}`
- Validation as in §C.4. Errors: 422; 404 (unknown institution).
- `date_of_birth` can be set once by the user; later changes go through support.

**`POST /v1/me/profile/photo`**
- Request: `{upload_key: str}` (from presign with purpose `profile_photo`, ≤ 2 MB, image/jpeg or png)
- Response 202: `{photo_status: pending}`
- Errors: 422 `invalid_upload`.
- Moderation in B1 is format, size and dimension checks only; image moderation by provider lands in B4. The status stays `pending` and the photo is not public until approved.

**`GET /v1/me/privacy`** and **`PUT /v1/me/privacy`**
- Request: `{leaderboard_visible?: bool, profile_private?: bool}`
- Response: privacy DTO
- A guardian opt-out (set via B8 PAR) cannot be overridden by the minor (403 `forbidden`).

**`POST /v1/me/consent/guardian/start`**
- Request: `{guardian_phone, guardian_relation: mother|father|guardian|other, consent_version}`
- Response 202: `{challenge_id, expires_at}`
- Errors: 422 (same as own phone); 409 (consent already active); 429.
- Tier T-otp.

**`POST /v1/me/consent/guardian/confirm`**
- Request: `{challenge_id, code}`
- Response 200: `{consent: {status: granted, version, granted_at}}`
- Errors: 401 `invalid_code`; 410.

**`GET /v1/consent-documents/{version}`**: `?lang=bn|en` → `{version, lang, body_markdown, published_at}`. Public.

**`GET /v1/reference/districts`** → `{items: [{id, division, name_bn, name_en, upazilas: [{id, name_bn, name_en}]}]}`. Public, cacheable for 1 day.

**`GET /v1/reference/institutions`**: `?q=` (≥ 2 chars), `?district_id=`, `?limit=` → `Page<{id, name_bn, name_en, kind, district_id}>`. Trigram search. T-read.

**`POST /v1/webhooks/facebook/data-deletion`**
- Form body: `signed_request`
- Response 200: `{url, confirmation_code}`
- Errors: 400 `bad_request` (bad signature, with no detail).
- Auth: Signed.

**`GET /v1/auth/social/facebook/deletion-status/{code}`** → `{status: received|completed, completed_at?}`. Public.

**`POST /v1/webhooks/facebook/deauthorize`**: form `signed_request` → 200 `{}`.

**`POST /v1/reports`**
- Request: `{target_type: user|display_name|profile_photo|post|other, target_id: uuid, reason: enum, text?: str (≤ 500)}`
- Response 201: `{report_id}`
- Rate limit: 20 per user per day. Text runs through `moderate`.

**`GET /v1/admin/moderation/reports`**: `?status=` → `Page<Report>`. Staff:moderation.

**`POST /v1/admin/moderation/reports/{id}:resolve`**
- Request: `{decision: dismiss|action_taken, note: str (≥ 5), restriction?: RestrictionInput}`
- Response 200. Audited. Idempotency required.

**`POST /v1/admin/moderation/restrictions`**
- Request: `{user_id, kind: mute|ban, scope: all|community|profile, reason: str (≥ 5), ends_at?: datetime}`
- Response 201. Audited. Idempotency required.
- A ban revokes all sessions immediately.

**`DELETE /v1/admin/moderation/restrictions/{id}`**: 204. Audited.

**`GET/POST/DELETE /v1/admin/moderation/terms[/{id}]`**
- POST `{lang: bn|en|banglish, term: str, severity: low|medium|high, category}`. The term is stored folded.
- Audited.

**`POST /v1/admin/role-grants`**
- Request: `{user_id, role_code, scope_type, scope_id?, reason}`
- Response 201
- Errors: 403 (you cannot grant roles above your own); 409 (an active duplicate). Audited.

**`DELETE /v1/admin/role-grants/{id}`**: 204. Audited.

**`GET /v1/admin/audit-log`**: `?actor_user_id=&target_type=&target_id=&action=&from=&to=&cursor=` → `Page<AuditEntry>`. Staff:audit.read. Maximum range 93 days per query.

**`PUT /v1/admin/runtime-config/{key}`**
- Request: `{value: json, reason: str}`
- Key allow-list: `kill.tutor`, `kill.photo_solve`, `kill.registrations`, `kill.payments`, `min_app_version.android`, `min_app_version.web`, `support.links`, `ratelimit.overrides`.
- Response 200. Audited.

**`GET /v1/config/client`** → `{kill_switches: {...}, min_app_version: {...}, support: {...}, server_time: datetime}`. Public. Edge cache 30 s.

**`GET /v1/uploads/{purpose}/presign`**
- `purpose` is `profile_photo` in B1; later builds add more.
- Query: `?content_type=&bytes=`
- Response: `{upload_url, fields?, key, expires_at, max_bytes}`
- Errors: 422 (type or size not allowed for the purpose). Tier T-upload.

**`GET /livez`** → `{status: "ok"}`. **`GET /readyz`** → 200 `{status: ok, checks: {db: ok, redis: ok}}` or 503 `{status: fail, failing: ["db"]}`.

---

## E. Testing strategy

Test infrastructure, created in this build and reused by all later builds:

- `tests/conftest.py`:
  - sets the env before app import;
  - `migrated` session fixture (`alembic upgrade head` once per xdist worker against a per-worker database cloned from a template);
  - `session` fixture (connection plus outer transaction, `join_transaction_mode="create_savepoint"`, rolled back);
  - `client` (HTTPX `AsyncClient` over `ASGITransport` with the session override);
  - `redis` (database index per worker, flushed per test);
  - `clock` (`FrozenClock` injected via dependency override);
  - `sms` (fake gateway);
  - `make_user()` and `auth_headers(user, roles)` factories.
- `tests/concurrency/conftest.py`: a real committed database (`CREATE DATABASE … TEMPLATE test_template`) per test module, for tests needing several connections. Marker `concurrency`.

| File | Type | Cases |
|---|---|---|
| `tests/core/test_settings.py` | unit | Prod refuses: wildcard CORS, fake SMS, memory queue, missing social secrets when enabled, short keys; local defaults load |
| `tests/core/test_health.py` | api | `/livez` 200 without dependencies; `/readyz` 503 naming db or redis; 200 when both are up; for each of the 5 apps |
| `tests/core/test_errors.py` | api | Each `AppError` maps to its envelope; validation 422 shape; 500 hides details and includes `request_id` |
| `tests/core/test_request_context.py` | unit | Valid `X-Request-ID` echoed; invalid one replaced; access log has no query string PII |
| `tests/core/test_logging_redaction.py` | unit | Phone, email, token, otp and answer_key keys redacted in nested dicts |
| `tests/core/security/test_jwt.py` | unit | Sign and verify; wrong `aud`; expired; tampered; unknown `kid`; key rotation with two kids |
| `tests/core/security/test_crypto.py` | unit | Round trip; ciphertext differs per call; tampered tag fails; key id header |
| `tests/core/test_ratelimit.py` | integration | Sliding window allows N and blocks N+1; `Retry-After`; per-key isolation |
| `tests/core/test_resilience.py` | unit | Breaker opens at 50% over 30 s, half-open probe, closes; retry backoff bounds |
| `tests/shared/test_bangla_text.py` | unit | NFC, zero-width, digits, folding pairs, Banglish folding examples ("nioton er sutro") |
| `tests/shared/test_dhaka_date.py` | unit | 17:59:59Z → same Dhaka date, 18:00:00Z → next date; Saturday week keys; month keys |
| `tests/modules/test_registry.py` | unit | 16 modules; schema list equals migration `b01_01`; OFF has no package |
| `tests/test_structure.py` | unit | Runs `check_file_length.py` and `check_boundaries.py` (also in CI) |
| `tests/entrypoints/test_exam_ingest_isolation.py` | integration | Subprocess imports the ingest app; `sqlalchemy` and `asyncpg` are not in `sys.modules` |
| `tests/entrypoints/test_worker_check.py` | integration | `--check` exits 0; a bad config exits 1 |
| `tests/modules/nfr/test_jobs_repo.py` | db | Enqueue; claim respects `run_at` and priority; lease expiry re-claim; `dedupe_key` uniqueness; dead after max attempts |
| `tests/concurrency/test_job_claim.py` | concurrency | 8 coroutines on separate connections claim 1,000 jobs: each claimed exactly once |
| `tests/modules/nfr/test_consumer_dedupe.py` | db | Same event twice → handler effects once; failure rolls back both the effect and the dedupe row |
| `tests/modules/nfr/test_outbox_relay.py` | integration | Events → Parquet in localstack S3 with the expected schema; `relayed_at` set; crash between upload and mark → rerun overwrites the same key, no duplicate rows in the Parquet set |
| `tests/modules/nfr/test_idempotency.py` | api | Replay returns the same body with `Idempotent-Replay`; different body → 422; concurrent same key → one execution (the other 409 `conflict` in-flight); keys scoped per user |
| `tests/modules/nfr/test_partition_maintenance.py` | db | Creates future partitions; drops expired droppable partitions only; never drops `audit_log` before 3 years |
| `tests/modules/ops/test_audited.py` | db | Change plus audit row in one transaction; a rollback leaves no audit row; before/after diff; PII redacted; `UPDATE audit_log` fails under `app_rw` |
| `tests/modules/auth/test_otp_send.py` | api | Normalisation variants; limits (3 per 15 min, 5 per day, IP limit); challenge required after failures; identical response for unknown numbers |
| `tests/modules/auth/test_otp_verify.py` | api | Success creates user, privacy defaults, session, tokens; wrong code decrements attempts; 6th attempt 429; expired 410; banned 403 |
| `tests/concurrency/test_otp_double_verify.py` | concurrency | Two parallel verifies of one challenge → one success, one 401/410 |
| `tests/modules/auth/test_tokens.py` | api | Refresh rotates; old refresh reuse revokes the family and the session; logout blocks the access token within the same second via `revoked_sess` |
| `tests/modules/auth/test_sessions.py` | api | List shows current; revoke another; cannot revoke someone else's (404); session cap of 10 |
| `tests/modules/auth/providers/test_google.py` | unit | Locally signed RS256 tokens with a fake JWKS: valid; wrong `aud`; wrong `iss`; expired; future `iat`; nonce mismatch; unknown `kid` triggers one refetch; rotated key accepted |
| `tests/modules/auth/providers/test_facebook.py` | unit | HTTPX `MockTransport`: valid `debug_token`; `is_valid=false`; wrong `app_id`; expired; `/me` without email; `appsecret_proof` present; Limited Login OIDC path; timeout → `ProviderError(unavailable)` |
| `tests/modules/auth/test_social_sign_in.py` | api | **Linking matrix:** new Google user created; Google verified email equal to an existing verified email → auto-link; Google unverified email → new user; Facebook with an email equal to an existing account → new user (no auto-link); existing identity → same user; banned user → 403; nonce reuse → 401; disabled provider → 404; under 13 with Facebook → 403 and nothing created; provider outage → 503 with fallback |
| `tests/concurrency/test_social_first_sign_in_race.py` | concurrency | Two parallel first sign-ins with the same identity → one user, two sessions |
| `tests/modules/auth/test_social_link.py` | api | Link from a session; identity in use elsewhere → 409; duplicate provider → 409; unlink last method → 409 `last_sign_in_method`; unlink with phone present → 204 |
| `tests/modules/auth/test_meta_callbacks.py` | api | Valid `signed_request` → unlink, audit, status URL; bad signature → 400; wrong algorithm → 400; deauthorise unlinks |
| `tests/modules/auth/test_pending_signup.py` | api | New phone or social identity without DOB → `needs_profile` and no `users` row; complete with DOB → user created; under-13 Facebook → 403 with nothing created; token reuse → 410 |
| `tests/modules/auth/test_step_up.py` | api | Unlink, phone change and deletion without `X-Step-Up-Token` → 403 `step_up_required`; dormant 180 days + new device → restricted mode; unlink without a verified phone → 403 `phone_required` |
| `tests/modules/auth/test_staff_sso.py` | api | Fake OIDC IdP: MFA `amr` → admin tokens; no MFA → 403 `mfa_required`; disallowed domain → 403; **every `/v1/admin/*` route rejects a user token and an admin token without `sso=true`** (table-driven from the route list); `seed_dev` tokens refused when `APP_ENV=prod` |
| `tests/core/test_body_limits.py` | api | 256 KB JSON accepted, 257 KB → 413; batch endpoints accept 1 MB |
| `tests/modules/auth/test_rbac.py` | unit + db | `can()` with global, subject and tenant scopes; super admin bypass is audited; grant above own role → 403; cache invalidated on revoke |
| `tests/modules/auth/test_profile.py` | api | Validation rules (§C.4); institution search; DOB set once; display-name moderation block |
| `tests/modules/auth/test_consent.py` | api | Under 18 → `needs_consent`; guardian OTP flow; same phone refused; withdrawn consent; latest version required |
| `tests/modules/auth/test_authz_matrix.py` | api (authorization) | Every B1 route × {anonymous, student, other student, staff without permission, staff with permission}: expected status (table-driven from the 14 index) |
| `tests/modules/com/test_moderate.py` | unit | Bangla, English and Banglish terms; folded variants; zero-width evasion; allow-list of clean words containing substrings |
| `tests/modules/com/test_restrictions.py` | api | Ban revokes sessions; mute blocks report creation; lift restores; all audited |
| `tests/modules/plan/test_sms.py` | integration | Template render with Bangla numerals; segment counting (GSM-7 vs UCS-2 boundaries); job sends via fake; gateway failure retries then dead; breaker |
| `tests/contract/test_event_envelope.py` | contract | `user.signed_in` envelope validates against `EventEnvelope` v1 |
| `tests/security/test_no_plaintext_pii.py` | regression | After the API suite, scan all text columns for phone and email patterns: none found |
| `tests/load/auth.js` (k6) | load (not in CI) | OTP verify and refresh at 200 req/s against staging; p95 < 150 ms excluding SMS |

Failure and recovery are covered by: relay crash and retry; worker killed mid-job (lease expiry); Redis down (rate limiter fails **open** for reads and **closed** for OTP send, and readiness reports redis); provider outage (breaker).

---

## F. Build completion

### F.1 Acceptance criteria (measurable)

1. `scripts/check.sh` passes locally and in CI with zero ruff, format, mypy, boundary or line-limit errors.
2. Coverage is ≥ 85% overall and ≥ 95% on every `[tool.critical_coverage]` path.
3. All 5 deployables start in Docker; `/readyz` is 200 for the HTTP ones and `--check` exits 0 for workers.
4. A user can sign up and sign in by phone OTP, Google (with a test token from the fake JWKS in CI, and a real Google test account on staging) and Facebook (a Meta test user on staging). The linking matrix tests pass.
5. Refresh reuse revokes the session within one request; logout blocks the access token immediately.
6. 1,000 jobs are claimed exactly once by 8 concurrent workers; a killed worker's jobs complete after lease expiry.
7. 10,000 outbox events relay to S3 Parquet with zero loss and zero duplicates in a replayed relay test.
8. Every admin write in B1 creates an audit row (asserted by `test_authz_matrix` and `test_audited`).
9. No plain-text PII in the database after the full test suite.
10. `alembic upgrade head`, `alembic check` and downgrade/upgrade round trips pass on PostgreSQL 17; a staging run behind PgBouncer in transaction mode passes the API suite.

### F.2 Deliverables

- The code and files of §C.3.
- Migrations `b01_01`–`b01_12`.
- Seed scripts and CSVs.
- The CI workflow.
- `backend/README.md`.
- The generated `backend/openapi.json` snapshot.
- A build report in the PR, listing: features done, test counts, coverage, deviations, and the proposed additions accepted or rejected.

### F.3 Definition of done

[`21_definition_of_done.md`](21_definition_of_done.md) applies in full: the build-level and PR-level checklists.

### F.4 Code quality

Every file is ≤ 200 lines and most are 50–150. There is no `utils.py`. Routers contain no business logic. No module imports another module's `internal`. All public functions are typed. No `# type: ignore` without a reason comment, and none in critical paths.

### F.5 Manual verification checklist

- [ ] On staging: OTP to a real BD number arrives (once the vendor is live); the code works once.
- [ ] Google sign-in from a test web page with Google Identity Services returns tokens.
- [ ] Facebook sign-in with a Meta test user; the data-deletion callback is configured in the Meta dashboard and returns a status URL that opens.
- [ ] Revoke a session from another device and confirm the first device gets 401 within 15 minutes, or immediately for the revoked session.
- [ ] Audit log search shows the role grant made during the check.
- [ ] Logs in JSON contain the request id and no phone numbers.

### F.6 Exit criteria before Build 2

All of F.1 holds, the PR is merged to `main`, staging is deployed from `main`, and the proposed additions below have been accepted into [01](01_database_design.md) or [14](14_api_contracts.md), or rejected.

---

## Proposed additions (resolved)

All three were **accepted** and applied: both Redis keys are in 01 §3.17, and `identity.data_requests` is created in this build (`b01_10`).

| Kind | Item | Reason |
|---|---|---|
| Redis key | `auth:grants:{user_id}` (actor grants cache, 60 s) | Avoids a DB read per request for `can()`. Add to 01 §3.17. |
| Redis key | `idem:lock:{user_id}:{key}` (in-flight idempotency lock, 30 s) | Prevents two concurrent executions of the same idempotent POST. Add to 01 §3.17. |
| Storage | Facebook deletion confirmation before `identity.data_requests` exists (B6) | B1 records the request in `ops.audit_log` with the confirmation code; the status endpoint reads it. Alternative: create `identity.data_requests` in B1 instead of B6 (recommended; it is small). |

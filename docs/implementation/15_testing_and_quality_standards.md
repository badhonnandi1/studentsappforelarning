# 15 · Testing and quality standards

**Date:** 2026-11-27 · Applies to every build from Build 1. Architecture rules: [`04`](04_backend_master_plan.md). Definition of done: [`21`](21_definition_of_done.md). Security tests: [`18`](18_security_architecture.md) §12. Load tests: [`17`](17_scalability_and_performance.md) §8.

Every build ends with all of the following at zero: lint errors, format diffs, mypy errors, failing tests, unapproved 200-line violations. Coverage must be at least 85% overall and 95% on critical paths (§5).

---

## 1. Tool stack

| Tool | Version floor | Role | Runs in |
|---|---|---|---|
| uv | ≥ 0.9 | Dependency resolution and lock (`uv.lock`), virtualenv, `uv run` | Local, CI |
| Ruff | ≥ 0.17 | Lint, import sorting, formatting | Pre-commit, CI |
| Mypy | ≥ 2.4 (strict) + pydantic plugin | Static types | Pre-commit (changed files), CI (all) |
| Pytest | ≥ 9.2 | Test runner | CI, local |
| pytest-asyncio | ≥ 1.2 | Async tests (§3.1) | CI, local |
| pytest-cov | ≥ 7.0 | Coverage with branches | CI |
| pytest-xdist | ≥ 3.8 | Parallel test workers | CI |
| HTTPX | ≥ 0.29 | `AsyncClient` + `ASGITransport` API tests; `MockTransport` for providers | Tests |
| respx | ≥ 0.22 | Route-level HTTPX mocking where `MockTransport` is too verbose | Tests |
| polyfactory | ≥ 2.22 | Typed factories for pydantic DTOs and SQLAlchemy models | Tests |
| time-machine | ≥ 2.19 | Only for code we do not control; our code uses the injected `Clock` | Tests |
| pre-commit | ≥ 4.3 | Local hooks | Local |
| import-linter + grimp | ≥ 2.17 | Layers and boundaries | Pre-commit, CI |
| pip-audit, Trivy, gitleaks | latest pinned in CI | Vulnerability and secret scanning | CI ([`18`](18_security_architecture.md) §10) |
| k6 | ≥ 1.3 | Load tests | Staging only |

All versions are pinned in `uv.lock`; the floors above are the minimums in `pyproject.toml`.

## 2. Central configuration (`backend/pyproject.toml`)

All tool configuration lives in `pyproject.toml` except `.pre-commit-config.yaml`, `.importlinter` and `.line-limit-exempt`.

```toml
[project]
name = "studyplatform-backend"
requires-python = ">=3.13,<3.14"

[dependency-groups]
dev = [
  "pytest>=9.2", "pytest-asyncio>=1.2", "pytest-cov>=7.0", "pytest-xdist>=3.8",
  "httpx>=0.29", "respx>=0.22", "polyfactory>=2.22", "time-machine>=2.19",
  "mypy>=2.4", "ruff>=0.17", "import-linter>=2.17", "pre-commit>=4.3",
]

[tool.ruff]
target-version = "py313"
line-length = 100
src = ["src", "tests", "migrations", "scripts"]

[tool.ruff.lint]
select = ["E","W","F","I","B","C4","UP","S","ASYNC","N","SIM","RUF","PT","T20","ARG"]
ignore = ["E501"]            # formatter owns line length

[tool.ruff.lint.isort]
known-first-party = ["app"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106", "S107", "S603", "ARG001"]
"migrations/versions/**" = ["N999"]

[tool.ruff.format]
quote-style = "double"
docstring-code-format = true

[tool.mypy]
python_version = "3.13"
strict = true
plugins = ["pydantic.mypy"]
mypy_path = "src"
explicit_package_bases = true
warn_unreachable = true
enable_error_code = ["ignore-without-code", "redundant-expr", "truthy-bool"]

[[tool.mypy.overrides]]
module = ["grimp.*", "asyncpg.*", "aioboto3.*"]
ignore_missing_imports = true

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
addopts = "-q --strict-markers --strict-config -p no:cacheprovider"
filterwarnings = ["error"]
markers = [
  "unit: pure functions and services with fakes; no I/O",
  "integration: real Postgres/Redis through repositories and services",
  "api: HTTP through ASGITransport against the FastAPI app",
  "db: schema, constraint, trigger, index and migration behaviour",
  "concurrency: several connections racing; uses a cloned database",
  "contract: cross-module DTOs, event payload schemas and OpenAPI snapshot",
  "slow: longer than 2 s; still in the merge gate",
  "eval: offline AI evaluation against recorded or live fixtures",
  "load: k6 scenarios (JavaScript, tests/load/) driven by pytest wrappers; never in the default run",
]

[tool.coverage.run]
branch = true
source = ["src/app"]
omit = ["src/app/entrypoints/*/__main__.py"]
concurrency = ["greenlet", "thread"]

[tool.coverage.report]
fail_under = 85
show_missing = true
skip_covered = true
exclude_also = ["if TYPE_CHECKING:", "raise NotImplementedError", "@overload", "\\.\\.\\."]
```

**Why pytest-asyncio with `asyncio_mode = "auto"` rather than anyio.** SQLAlchemy async, asyncpg and redis-py all run on asyncio only, so trio support from anyio is unused. One session-scoped loop lets the session-scoped engine and Redis pool be shared, which removes the per-test connection cost. The deleted skeleton used `pytest.mark.anyio`; Build 1 switches to pytest-asyncio and records this in its build report.

Default commands (`scripts/check.sh`, run in this order; it stops on the first failure):

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src tests migrations scripts
uv run lint-imports
uv run python scripts/check_boundaries.py
uv run python scripts/check_file_length.py
uv run pytest -n auto -m "not eval and not load" --cov --cov-report=xml --cov-report=term
uv run python scripts/check_coverage_paths.py coverage.xml
```

## 3. Test infrastructure

### 3.1 Services under test

| Dependency | In tests | Why |
|---|---|---|
| PostgreSQL 17 + pgvector, pg_trgm, ltree | **Real**, from `docker-compose.yml` service `db` (image `pgvector/pgvector:0.8.1-pg17`) with database `app_test` | Constraints, triggers, partitions, `SKIP LOCKED`, RLS and HNSW cannot be faked. |
| Redis 7 | **Real**, compose service `redis`, database index per xdist worker (`/1`…`/15`), flushed per test | Rate limits use Lua scripts, leaderboards use sorted sets with `ZINCRBY`/`ZREVRANGE`, telemetry uses streams (`XADD`/`XREADGROUP`). fakeredis lags on Lua semantics and stream consumer groups, and a mismatch would hide exactly the bugs these tests exist for. |
| SQS, S3 | **localstack** (SQS, S3 only), compose service `aws` | Exam ingest acknowledgement depends on `SendMessage` success semantics, and the relay writes Parquet to S3. In-memory fakes are used only for unit tests via the `AnswerBatchQueue` protocol. |
| LLM, OCR, embeddings | **Fakes** implementing the provider protocols, with recorded responses in `tests/fixtures/ai/` | Deterministic, free, offline. Live providers run only in the `eval` suite (§7). |
| SMS, FCM, payment gateways, Google, Facebook, Apple | HTTPX `MockTransport` per adapter (respx where many routes) | Adapters are tested at the HTTP boundary, including timeouts and malformed bodies. |
| Time | `FrozenClock` fixture injected through `core.clock.Clock` | Streaks, settlement, exam windows and token expiry depend on time; nothing calls `datetime.now()`. |

### 3.2 Fixtures (`tests/conftest.py` and `tests/fixtures/*.py`, each ≤ 200 lines)

| Fixture | Scope | Behaviour |
|---|---|---|
| `settings` | session | Builds `Settings(APP_ENV="test", …)` from `TEST_DATABASE_URL` etc. Exits with a clear message if Postgres is unreachable. |
| `migrated_db` | session | `alembic upgrade head` once on `app_test`; then `CREATE DATABASE app_test_tmpl TEMPLATE app_test` for concurrency clones. |
| `engine` | session | `create_async_engine(url, poolclass=NullPool)` per xdist worker. |
| `session` | function | Opens a connection, `await conn.begin()`, yields `AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")`, rolls back at the end. Service-level `session.begin()`/`commit()` become savepoints. |
| `client` | function | `create_app("api")` with `dependency_overrides[get_session] = lambda: session`; `AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`. Variants: `gateway_client`, `ingest_client`. |
| `actor_factory` | function | Creates a user with roles and returns `(user, auth_headers)` signed with the test EdDSA key. |
| `clone_db` | function (marker `concurrency`) | `CREATE DATABASE c_<worker>_<n> TEMPLATE app_test_tmpl`, yields an engine with a real pool (size 10), drops the DB after. Used where several connections must race (R1–R20 in [`01`](01_database_design.md) §5.2). |
| `redis` | function | Real client on the worker's DB index; `FLUSHDB` after each test. |
| `clock` | function | `FrozenClock(datetime(2026, 11, 26, 17, 58, 3, tzinfo=UTC))` with `advance()`; overridden into the app. |
| `fake_llm`, `fake_ocr`, `fake_embedder` | function | Record calls; return fixtures keyed by prompt version and input hash; can be told to fail, time out or stream slowly. |
| `mock_http` | function | `respx.mock` router shared by provider adapters. |
| `aws` | session | localstack SQS queue and S3 bucket names unique per worker. |
| Model factories | — | `UserFactory`, `QuestionVersionFactory` (published, bilingual, KaTeX pre-rendered), `SessionFactory`, `ExamFactory`, etc., in `tests/factories/<module>.py`. Factories insert through repositories, never through raw SQL, so tests follow the same constraints. |

### 3.3 API test pattern

```python
async def test_replayed_answer_returns_stored_result(client, actor_factory, published_session):
    _, headers = await actor_factory(role="student")
    body = answer_body(published_session, selected=["kha"])
    first = await client.post(f"/v1/practice/sessions/{published_session.id}/answers", json=body, headers=headers)
    again = await client.post(f"/v1/practice/sessions/{published_session.id}/answers", json=body, headers=headers)
    assert first.status_code == again.status_code == 200
    assert again.json() == {**first.json(), "duplicate": True}
```

Every endpoint in [`14`](14_api_contracts.md) gets at least: happy path, validation failure (422), unauthenticated (401), wrong owner or missing permission (403 or 404, never a data leak), and its idempotency replay if marked **R**.

## 4. Test pyramid and markers

| Layer | Marker | Share of tests | Typical speed | What it proves |
|---|---|---|---|---|
| Unit | `unit` | ~55% | < 10 ms | Pure rules: XP, level formula, streak and settlement, effective time, Dhaka dates, answer-key checking per type, blueprint selection, tie-breaks, contiguity check, quota maths, Bangla normalisation and Banglish folding, maths canonicalisation, citation verification, linking rules. Table-driven. |
| Integration | `integration` | ~25% | 20–200 ms | Services with real Postgres and Redis: the answer transaction, outbox write, job claim, entitlement union, social sign-in find-or-create. |
| API | `api` | ~12% | 30–300 ms | HTTP contracts, auth, error envelope, rate-limit headers, pagination. |
| Database | `db` | ~3% | — | Every `CHECK`, unique and partial unique index, the `verifier_id <> author_id` check, partition routing, `REVOKE` on `audit_log`, RLS policies (B8), `alembic check` (models match migrations), downgrade of the latest migration. |
| Concurrency | `concurrency` | ~2% | 0.5–5 s | Each race R1–R20 in [`01`](01_database_design.md) §5.2, reproduced with `asyncio.gather` over separate connections on a cloned database, asserting exactly-once effects. |
| Contract | `contract` | ~3% | fast | Event envelope and payload schemas (golden JSON per `event_type` and `schema_version`), cross-module DTOs, the OpenAPI snapshot diff, the module registry matching migrations. |
| Eval | `eval` | separate | minutes | AI gates (§7). |
| Load | `load` | separate | minutes–hours | [`17`](17_scalability_and_performance.md) §8. |

Regression tests: every bug fix adds a test named `test_regression_<issue>_<what>` in the module's suite that fails before the fix.

Failure and recovery tests: each external dependency has a test where it times out, returns 5xx, returns malformed data, and recovers (circuit breaker closes after probe). Workers have kill-mid-job tests (lease expiry → re-claim → no duplicate effect).

## 5. Coverage

- **Overall:** `fail_under = 85` with branch coverage, measured over `src/app`.
- **Critical paths: 95% line and branch**, enforced by `scripts/check_coverage_paths.py` (≈ 90 lines). It reads `coverage.xml`, groups files by the globs below and fails listing each group below threshold. The list is in the script, so adding a path is a reviewed change.

| Group | Globs | From build |
|---|---|---|
| auth-tokens | `modules/auth/internal/services/{tokens,social_*,otp}*`, `…/services/session*`, `…/services/{staff_sso,step_up,pending_signup}*`, `…/providers/**`, `core/security/**` | 1 |
| idempotency-outbox-jobs | `core/idempotency*`, `modules/nfr/internal/services/{outbox,jobs,relay}*`, `modules/nfr/internal/jobs/**` | 1 |
| audit | `modules/ops/internal/services/audit*` | 1 |
| verification-workflow | `modules/cms/internal/services/{workflow,verification}*` | 2 |
| answer-transaction | `modules/prac/internal/services/answer_*`, `modules/anl/internal/services/projection*` | 3 |
| gamification-rules | `modules/gam/**`, the whole module, so `gam.repair_from_answer`, the consumers and the key builders are included (R-27) | 3 |
| entitlements | `modules/pay/internal/services/entitlement*`, `…/quota*` | 3 |
| rescoring | `modules/prac/internal/jobs/rescore_correction.py`, `modules/prac/internal/services/adjustments.py`, `modules/cms/internal/rescoring/**` (the PRAC job owns rescoring; CMS only consumes progress events, R-03) | 3 |
| ai-gates | `modules/ai/internal/services/{gate,quota,cache,verify,lock}*` | 4 |
| exam-ingest-close | `modules/exam/ingest/**` (public subpackage), `modules/exam/lock_registry.py`, `modules/exam/internal/consumers/**`, `modules/exam/internal/services/close_*`, `modules/exam/internal/scoring/**`, `modules/exam/internal/merit/**`, `modules/exam/internal/services/{registration,attempt_start,token_refresh}.py` | 5 |
| payments | `modules/pay/internal/services/**`, `modules/pay/internal/jobs/**` (includes `pay.process_provider_event`, sweeper, duplicate refund, reconciliation), `modules/pay/internal/providers/**` | 6 |
| marking | `modules/ai/internal/services/marking_*`, `modules/ai/internal/pipeline/release.py`, `modules/inst/internal/services/{submission,release,review_queue}*` | 4, 6 |
| user-lifecycle | `modules/*/internal/events/user_lifecycle.py`, `modules/auth/internal/services/data_requests.py` | 6 |
| tenant-isolation | Every file under `migrations/helpers/rls.py` and `core/db/tenant*`, plus the **RLS policy test suites** `tests/contract/test_tenant_*.py` and `tests/modules/*/db/test_rls_*.py`. These must all run and pass, as an execution gate, not only as a coverage figure (R-27). | 8 |

**No tests written only to raise the number.** Reviewers reject tests that assert nothing meaningful (calling a function without checking an outcome), tests of trivial getters, and tests that mock the unit under test. Uncovered defensive branches get `# pragma: no cover` only with a one-line reason, and only for branches unreachable in tests (e.g. `assert_never`).

## 6. Testing throughout the builds

- **Test-first where rules are subtle.** GAM rules (B3), exam close and contiguity (B5), and payment capture (B6) start by writing the table-driven cases as failing tests, then the code. B3 starts with the v2 §5.5 worked example and 20 clock and duplicate cases (midnight, Saturday rollover, month end, reboot fallback to receipt time, skewed device clock, replay from another user, settlement at 06:00, late sync after settlement, key correction both ways).
- **Every step in a build's section C ends with `scripts/check.sh` green.** A build is never merged with skipped (`xfail`) tests except tests for later builds, which live on their build branch.
- **Earlier builds stay green.** The whole suite runs on every PR; later builds may not weaken earlier tests. A changed earlier assertion needs a note in the PR explaining the behaviour change and the design reference.
- **Replay tests** (v2 §8.2): from B3, a seeded generator produces 10,000 synthetic answers in CI (1 million nightly on staging) with 5% duplicates and reordering, and asserts identical projections and no double XP.

## 7. AI evaluation and regression (from B4)

| Suite | Trigger | Data | Gate |
|---|---|---|---|
| `eval-smoke` (marker `eval`, recorded) | Every PR touching `modules/ai/**` or `prompts/**` | 50 items per route with recorded provider outputs; checks pipeline logic, verifier, cache privacy | 100% pass (deterministic) |
| `eval-subset` (live provider) | Merge to `main` touching prompts or routing | 200 items stratified per route and subject | No regression > 2 points versus the last accepted run on any v2 §4.8 metric |
| `eval-full` (live) | Before release of a prompt or model change; weekly | Full v2 §4.8 sets (≥ 1,500 tutor, 400 maths, 500 OCR, 300 safety, cache privacy) | v2 §4.8 targets; result stored in `ai.eval_runs`, prompt marked passing in `ai.prompt_versions` |
| `marking-accuracy` | Before any marking model or prompt change | ≥ 400 double-marked answers per subject | v2 §4.10 gate; publishes `ai.accuracy_reports` |

Eval data contains no real student PII; consented handwriting sets are stored in a restricted bucket and never committed to the repo.

## 8. Event and API contract tests

- Each event type has a pydantic model in its producer's `contracts/` and a golden JSON file `tests/contract/events/<type>.v<n>.json`. Producer tests assert the outbox row validates against the model; consumer tests load the golden file. A schema change bumps `schema_version` and keeps the old consumer path until all old rows are processed.
- `backend/openapi.json` is regenerated in CI; any diff fails unless the PR includes the regenerated file.

## 9. The 200-line rule

`scripts/check_file_length.py` (≈ 80 lines):

- Counts **physical lines** (`len(text.splitlines())`) in every tracked file matching: `backend/src/**/*.py`, `backend/tests/**/*.py`, `backend/migrations/**/*.py`, `backend/scripts/**/*.py`, `backend/**/*.sql`, `edge/src/**/*.ts`, `edge/test/**/*.ts`, `backend/prompts/**/*.md` (prompt files are code).
- Excludes `docs/**`, Markdown outside `prompts/`, and the paths listed in `backend/.line-limit-exempt`.
- `.line-limit-exempt` may list **generated files only**, one per line with a reason and approver: initially `uv.lock` (generated by uv) and `openapi.json` (generated by FastAPI), plus `edge/package-lock.json`. Adding a line requires supervisor approval in the PR.
- Output: each offending path with its line count and the hint "split by subject"; exit code 1. Runs in pre-commit and CI.
- Fixtures over 200 lines (eval sets, golden payloads) are stored as data files (`.json`, `.jsonl`), which are not code and not counted.

## 10. Pre-commit (`.pre-commit-config.yaml`)

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: check-yaml
      - id: check-toml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: detect-private-key
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.17.6
    hooks:
      - id: ruff-check
        args: ["--fix"]
      - id: ruff-format
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.28.0
    hooks:
      - id: gitleaks
  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy
        language: system
        types: [python]
        require_serial: true
      - id: import-boundaries
        name: import boundaries
        entry: bash -c 'uv run lint-imports && uv run python scripts/check_boundaries.py'
        language: system
        pass_filenames: false
        types: [python]
      - id: line-limit
        name: 200-line limit
        entry: uv run python scripts/check_file_length.py
        language: system
        pass_filenames: false
```

(Paths are relative to `backend/`; the repo-root config uses `files: ^backend/` filters.)

## 11. CI quality gates

Merge to `main` requires every job green ([`19`](19_devops_and_deployment.md) §3 has the workflow):

| Gate | Fails when |
|---|---|
| format, lint | any diff or finding |
| types | any mypy error |
| boundaries | an import-linter contract or a module-internal import breaks; an import cycle between modules |
| line limit | any non-exempt file > 200 lines |
| migrations | `alembic upgrade head` fails on an empty DB; `alembic check` finds model drift; the latest migration's downgrade fails; a migration is not expand-compatible (lint script checks for `DROP COLUMN`, `ALTER … TYPE`, `NOT NULL` without default outside a contract migration) |
| tests | any failure; coverage < 85% overall or < 95% on a critical group |
| contract | OpenAPI or event golden file drift |
| security | pip-audit high/critical, Trivy high/critical in the image, gitleaks finding |
| eval-smoke | for AI changes |

## 12. Review rules

- PRs ≤ ~600 changed lines of non-generated code where possible; a build is delivered as a sequence of PRs following section C steps.
- At least one reviewer; two for critical-path groups (§5) and migrations.
- Reviewer checklist: business logic only in services; ownership checks on every id read; no cross-module table access; transaction boundary matches [`01`](01_database_design.md) §5.1; idempotency for R endpoints; tests cover the failure paths listed in the build document; no PII in logs.

## 13. Flaky tests and test data

- **Flaky policy:** a test that fails then passes on retry is quarantined within one working day with a tracked issue and owner (marker `flaky` added only through the quarantine PR). Quarantined tests still run nightly; fix or delete within 10 working days. CI does not auto-retry tests.
- Concurrency tests use deterministic barriers (`asyncio.Event`) instead of sleeps.
- **Test data:** synthetic only. Phone numbers from the reserved test block `+8801700000000–+8801700009999`, which matches the B1 phone regex `+8801[3-9]…`. The SMS adapter never sends to the block, a fixed test OTP is accepted, and the block is honoured only when `APP_ENV` is `test` or `dev` (R-31); names from a fixed synthetic Bangla and English list; questions authored for tests (`tests/fixtures/content/`), never copied from the real bank or guidebooks. No production data in any non-production environment except the restore drill's isolated account ([`19`](19_devops_and_deployment.md) §7).
- Bangla text fixtures cover conjuncts, nukta forms, zero-width joiners, Bangla numerals and mixed Banglish, so normalisation and search tests exercise real edge cases.

## 14. Optional: mutation testing

`mutmut` may run monthly on the gamification-rules and exam-close groups. Surviving mutants become new test cases. It is not a merge gate.

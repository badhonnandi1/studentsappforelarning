# 19 · DevOps, deployment and observability

**Date:** 2026-11-27 · Runtime shape: [`04`](04_backend_master_plan.md) §1. Quality gates: [`15`](15_testing_and_quality_standards.md) §11. Security: [`18`](18_security_architecture.md). Backups: [`01`](01_database_design.md) §5.8.

---

## 1. Local development (Docker)

`backend/docker-compose.yml` (local and CI only):

| Service | Image | Purpose |
|---|---|---|
| `db` | `pgvector/pgvector:0.8.1-pg17` | Postgres 17 with pgvector; init script creates `app` and `app_test`, enables `vector`, `pg_trgm`, `ltree`, `btree_gist` |
| `pgbouncer` | `edoburu/pgbouncer` (transaction mode) | Optional profile `pooling`, to test asyncpg settings against PgBouncer |
| `redis` | `redis:7.4-alpine` | Rate limits, quotas, boards, streams |
| `aws` | `localstack/localstack` (SERVICES=sqs,s3) | Exam answer queue, uploads and event-log buckets |
| `api`, `workers`, `ai-gateway`, `exam-ingest`, `exam-consumers` | the app image with different commands | Profile `app`; hot reload with a bind mount |

Developer commands (`backend/scripts/`, each ≤ 200 lines; no Makefile needed):

| Command | Does |
|---|---|
| `scripts/dev-up.sh` | `docker compose up -d db redis aws`, wait for health, `alembic upgrade head` |
| `scripts/seed.py` | Idempotent synthetic seed: tracks and the SSC 2028 Physics tree, 200 bilingual questions, products, quotas, reward rules v1, test users per role (phones from the test range, [`15`](15_testing_and_quality_standards.md) §13) |
| `scripts/check.sh` | All quality gates ([`15`](15_testing_and_quality_standards.md) §2) |
| `uv run uvicorn app.entrypoints.api:app --reload` | Run the API; similar for other entry points |
| `scripts/openapi.sh` | Regenerate `openapi.json` |

Fake providers are the default locally (`SMS_PROVIDER=console`, `AI_PROVIDER=fake`, `PAYMENT_PROVIDERS=sandbox`), so no external account is needed to develop or test.

## 2. Environments

| | dev (local) | test (CI) | staging | perf | prod |
|---|---|---|---|---|---|
| Purpose | Development | Automated tests | Integration, demos, sandbox payments | Load tests ([`17`](17_scalability_and_performance.md) §8) | Users |
| Infra | Docker compose | Compose services in GitHub Actions | AWS ap-south-1, small sizes | Clone of staging sized per stage, created on demand by Terraform | AWS ap-south-1 Multi-AZ, Cloudflare |
| Data | Synthetic seed | Per-test | Synthetic + content team's test bank | Synthetic at scale | Real |
| Providers | Fakes | Fakes + localstack | Sandboxes (bKash sandbox, aggregator sandbox, Play test track, FCM test project, SMS test sender), AI live with a low budget | Fakes for SMS and payments; AI fake with real latency, small live share | Live |
| Settings | `APP_ENV=local` | `test` | `staging` | `staging` | `prod`; validator refuses unsafe values ([`18`](18_security_architecture.md) §3 API8) |
| Docs (`/docs`) | On | On | On, behind staff auth | Off | Off |
| Secrets | `.env` fakes | CI secrets (fakes) | Secrets Manager | Secrets Manager | Secrets Manager |

## 3. CI/CD (GitHub Actions)

### 3.1 Pull request workflow (`.github/workflows/backend-ci.yml`)

| Job | Steps | Cache |
|---|---|---|
| `lint` | `uv sync --frozen`; ruff format check; ruff check; mypy; import-linter; `check_boundaries.py`; `check_file_length.py` | uv cache keyed on `uv.lock` |
| `test` (matrix of 4 xdist shards) | services: Postgres (pgvector image), Redis, localstack; `alembic upgrade head`; `pytest -n auto -m "not eval and not load" --cov`; upload `coverage.xml` | uv cache |
| `coverage` | merge shard reports; `fail_under 85`; `check_coverage_paths.py` | — |
| `migrations` | empty DB upgrade; `alembic check`; downgrade one step and upgrade again; expand-only lint on new migrations | — |
| `contract` | regenerate OpenAPI and compare; event golden files | — |
| `security` | `pip-audit`; gitleaks; build image; Trivy scan (fail on high/critical) | Docker layer cache |
| `eval-smoke` | only when `modules/ai/**` or `prompts/**` changed; recorded fixtures | — |
| `edge` (from B5) | `edge/`: lint, typecheck, unit tests (Vitest), line limit | npm cache |

All jobs are required checks on `main`. Typical PR time target: < 12 minutes.

### 3.2 Main branch workflow (`backend-deploy.yml`)

1. Re-run the PR checks on the merge commit.
2. `eval-subset` with the live provider when AI files changed ([`15`](15_testing_and_quality_standards.md) §7).
3. Build multi-arch (arm64) image once, tag with the commit SHA, sign with cosign, push to ECR.
4. **Deploy to staging:** run the migration task (§5), then update every ECS service; run smoke tests (sign-in with a test OTP, start a session, answer, tutor message with the fake provider in staging's canary mode, exam ingest round trip).
5. **Production promotion:** manual approval (engineering lead) on a protected environment; blocked automatically during an exam freeze window (§6.3).
6. **Production:** migration task, then blue/green per service with a 10% canary (§6.2).

## 4. Branching and pull requests

- **Trunk-based** on `main`. Each build uses short-lived branches `build/NN-<slug>-<step>` (for example `build/03-learning-loop-answer-tx`), merged by squash. Branches live under 3 days where possible.
- **PR template** (`.github/pull_request_template.md`): build and step reference; features touched (IDs); migrations (expand or contract); new endpoints (must exist in [`14`](14_api_contracts.md)); tests added (by marker); risk and rollback; screenshots of dashboards for performance-sensitive changes; checklist from [`21`](21_definition_of_done.md).
- **Size:** ≤ ~600 changed lines of non-generated code; migrations reviewed by two people; critical-path groups ([`15`](15_testing_and_quality_standards.md) §5) need two reviewers.
- **Commits:** imperative subject ≤ 72 characters, body says why.
- **Release notes:** generated per production deploy from PR titles with feature IDs.

## 5. Migration automation

- Migrations run as a **one-off ECS task** (`alembic upgrade head`) using the migration role, before any service update. The deploy stops if it fails.
- **Expand → migrate → contract** (v2 §8.3): every migration must work with the previous application version.
  - Expand: add nullable columns, new tables, new indexes `CONCURRENTLY` (in their own migration with `autocommit_block`), new check values.
  - Migrate: backfill in a job, in batches, outside the migration.
  - Contract: drop or tighten in a later release after the old code is gone, marked `# contract` in the file header so the expand-only lint permits it.
- Long operations: `SET lock_timeout = '2s'` at the start of each migration; retries on lock timeout by the task (3 tries).
- Partitions are not created by migrations beyond the initial set; the partition-maintenance job creates future partitions daily and alerts if fewer than 2 future partitions exist.
- Rollback never requires a schema downgrade; downgrades exist for development and CI only.

## 6. Deployment

### 6.1 Infrastructure (Terraform)

- Repository `infra/` with modules: `network` (VPC, private subnets in 3 AZs, NAT, VPC endpoints for S3, SQS, Secrets Manager, ECR), `ecs` (cluster on Graviton/ARM, one service per deployable), `rds` (Postgres 17 Multi-AZ, parameter group, replica), `pgbouncer` (ECS service), `redis` (two ElastiCache replication groups: **general** for caches, quotas, boards and telemetry; **exam**, Multi-AZ with automatic failover, `maxmemory-policy noeviction`, AOF `appendfsync everysec`, for `exam:*` and `exam_lock:*` only; R-09), `sqs` (exam answer queue + DLQ, standard), `s3` (uploads, event log with Object Lock, archives), `cloudflare` (DNS, WAF rules, rate limits, Workers, R2), `observability` (managed Grafana/Prometheus or vendor, alarms), `iam` (task roles, GitHub OIDC).
- State in S3 with DynamoDB locking; `terraform plan` in PRs touching `infra/`, apply by pipeline only.

### 6.2 Release strategy

- **Blue/green** through CodeDeploy for ECS per service: shift **10% canary for 10 minutes**, then 100%.
- **Automatic rollback** on CloudWatch alarms during the canary: 5xx rate > 1% (or 2× baseline), p95 latency > 1.5× baseline, error-budget burn alarm, worker crash loop.
- **Rollback target:** previous image within 5 minutes (v2 §8.3); kill switches cover feature-level rollback without a deploy.
- Workers and consumers deploy with graceful shutdown: stop claiming, finish in-flight jobs (≤ 60 s), release leases; SQS visibility timeouts let unfinished messages return.
- `exam-ingest` deploys only outside exam windows; it is pre-scaled one hour before an exam to the rehearsed per-instance rate.

### 6.3 Exam freeze

No production deploys, migrations or config changes (except control-room actions and kill switches) from **24 hours before to 2 hours after** a major live exam, meaning one with **≥ 5,000 registrants** (the same rule as [`09`](09_build_05.md) §C.7). The deploy pipeline reads the exam schedule from `GET /v1/admin/exams?kind=live&from=now` and blocks promotion during freezes.

### 6.4 Health and readiness

| Endpoint | Checks | Used by |
|---|---|---|
| `/livez` | Process alive (no I/O) | ECS container health |
| `/readyz` | Per deployable: api (Postgres via PgBouncer, Redis), ai-gateway (Postgres, Redis; provider breakers reported but not failing), exam-ingest (exam Redis, SQS `GetQueueAttributes`), workers and consumers (`--check` CLI: DB, Redis, SQS, queue names) | ALB target health, deploy gates |

### 6.5 Cloudflare

- Proxied DNS for `api.`, `ai.`, `ingest.`, `admin.`; WAF managed rules; bot fight mode off for API paths (mobile clients), custom rules instead.
- Rate limits per IP for `/v1/auth/*` and `/v1/ingest/*`; edge caching for public read endpoints with short TTLs (`/v1/tracks`, trees, catalogue, `/v1/config/client`).
- Workers: `/edge/time`, `/edge/exams/{id}/key`, signed media URLs; R2 for papers and media.
- Origin locked to Cloudflare IP ranges plus authenticated origin pulls.

## 7. Backups and disaster recovery

Targets and retention in [`01`](01_database_design.md) §5.8. Automation:

- RDS automated backups with PITR; daily snapshot copy to a second region by AWS Backup plan.
- S3 versioning and cross-region replication for the event log and exam archives.
- **Quarterly restore drill** (scripted in `infra/drills/restore.sh`): restore the latest snapshot to an isolated account, run `alembic current`, row-count and checksum queries, a projection rebuild on a 0.1% sample, and record RTO and RPO in `docs/drills/`. First drill is a Build 6 exit criterion (v2 §8.2).
- DR runbook for region loss: promote the cross-region snapshot, repoint DNS, accept RPO of the last copy (target 24 h for full region loss, documented as a risk).

## 8. Observability

### 8.1 Logging

- structlog JSON to stdout, shipped by the ECS log driver. Fields: `ts`, `level`, `service`, `version`, `env`, `request_id`, `trace_id`, `span_id`, `user_id` (pseudonymous id only), `route`, `status`, `duration_ms`, `module`, `event`.
- Request id: accepted from the edge (`CF-Ray` copied into `X-Request-ID` by Cloudflare transform rules) if it matches `[A-Za-z0-9._-]{1,64}`, otherwise generated; echoed in responses and error envelopes; copied into outbox `metadata.request_id` and job payloads so worker logs join to the original request.
- PII redaction processor ([`18`](18_security_architecture.md) §7). Log retention 30 days hot, 1 year archived.

### 8.2 Tracing

OpenTelemetry SDK with FastAPI, SQLAlchemy, asyncpg, redis, HTTPX instrumentations, exported via OTLP to the collector. **Justified for:** the answer transaction (DB spans), the tutor pipeline (gate → cache → retrieve → provider → verify), payments (provider calls), and exam consumers; trace context is propagated through outbox metadata into jobs. Sampling: 10% head sampling in prod plus 100% of errors and slow requests (tail sampling at the collector); 100% in staging.

### 8.3 Metrics

| Area | Metrics |
|---|---|
| API | Request rate, error rate (4xx/5xx by code), latency histograms by route; rate-limit rejections by tier |
| Database | Connections, PgBouncer wait time and pool saturation, transaction rate, slow queries (`pg_stat_statements` top 20), replication lag, deadlocks, autovacuum on `jobs` and `outbox`, partition count ahead |
| Redis | Hit rate per cache family, memory, CPU, evictions, command latency |
| Jobs | Queue depth and oldest-job age per queue, claim latency, success/failure, dead jobs, worker utilisation |
| Outbox | Unrelayed rows, relay lag (age of oldest unrelayed), events/s by type |
| Learning | Answers/s, duplicate rate, reward-pending rate (GAM savepoint failures), notebook recompute time |
| AI | Messages/s, first-token latency, cache hit rate, provider error rate, breaker state, tokens and cost per route per hour, quota rejections, verification failures, `not_sure` rate |
| Exam (live dashboard) | Participants online, batches/s, ack latency p50/p99, SQS depth and age, DLQ depth, consumer lag, scoring progress, close-run status, contiguity gaps |
| Payments | Orders by state, capture latency, webhook failures, reconciliation exceptions open and age |
| Notifications | Sends by channel, delivery failures, SMS cost per hour by prefix |

### 8.4 SLOs and alerting

| SLO | Objective | Alert |
|---|---|---|
| Journey availability (sign-in, answer save, paper/key fetch, exam ack) | 99.9% monthly (43 min budget), measured at the edge | Multi-window burn rate: page at 14.4× over 1 h and 5 min; ticket at 6× over 6 h |
| Exam acknowledgement in exam windows | 99.95% within 2 s | Page immediately on 5-minute breach |
| API latency | p95 < 300 ms | Ticket when over for 30 min; page at > 1 s for 10 min |
| Outbox lag | p95 < 2 s for boards/notifications | Page if oldest unrelayed > 5 min |
| Job queue | Oldest job age < 60 s on `notify`, `payments` | Page at > 5 min |
| AI | Tutor availability tracked separately (not in the 99.9% budget) | Ticket on breaker open > 10 min; page on global budget breaker |
| Payments | Reconciliation exceptions closed within 48 h | Ticket at 24 h, page at 48 h |
| Data integrity | Weekly 1% rebuild mismatches = 0; contiguity gaps = 0 | Page on any |

Errors and crashes go to **Sentry** (backend, with PII scrubbing; clients have their own projects in the frontend phase).

### 8.5 On-call and incident response

- Rota from launch: primary and secondary, weekly, with exam-day coverage by the exam lead and platform engineer on site.
- Severity: SEV1 (exam answers at risk, sign-in or answer save down, data exposure), SEV2 (tutor down, payments failing, major degradation), SEV3 (partial or internal).
- Runbooks in `docs/runbooks/` (one page each, created by the build that introduces the component):

| Runbook | Build | Core steps |
|---|---|---|
| Outbox or job backlog | 1 | Identify the stuck kind, scale the queue's workers, inspect dead jobs, replay |
| Database failover and slow primary | 1 | Confirm Multi-AZ failover, check PgBouncer reconnects, kill long queries, enable kill switches for heavy features |
| AI outage or budget breach | 4 | Confirm breaker, switch tutor kill switch if needed, communicate, process `pending_questions` on recovery |
| Exam day | 5 | T−24 h checklist (freeze, papers frozen, scaling, push), live dashboard thresholds, extend time, invalidate question, SQS throttling, consumer loss, hard close and contiguity failure handling |
| Payment outage and reconciliation | 6 | Switch payments kill switch, keep pending orders polling, run reconciliation, resolve exceptions |
| Data exposure | 6 | Revoke tokens and sessions, rotate keys, preserve audit evidence, legal notification under PDPA (D4) |

Every SEV1 and SEV2 gets a blameless review within 5 working days with tracked actions.

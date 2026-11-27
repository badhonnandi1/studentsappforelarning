# Build 1 report (draft, finalised at step 13)

Branch `build/01-platform-identity`. One commit per §C.1 step. Supervisor sign-off on S-1 to S-12
is still pending (00 A.5); the plan's defaults are used.

## Progress

| Step | Scope | State |
|---|---|---|
| 1 | Tooling skeleton | done |
| 2 | Settings, logging, errors, clock, ids, HTTP app | done |
| 3 | core.db, module registry, `b01_01`, test databases | done |
| 4 | Redis, rate limits, resilience, storage, security, shared helpers | done |
| 5 | NFR: queue, outbox, relay, consumers, idempotency, runtime config, partitions | done |
| 6 | OPS: `b01_05` audit log, `audited()`, audit search, runtime-config admin | done |
| 7 | Entry points: api, workers, ai_gateway, exam_ingest, exam_consumers | done |
| 8 | PLAN SMS: `b01_11`, gateways, templates, `send_sms`, `plan.sms.send` | done |
| 9–13 | AUTH, social, staff SSO, COM, seeds, hardening | pending |

## Deviations

### Environment and tooling
- **Local S3:** MinIO instead of localstack. SQS and KMS are not emulated; local KMS is an AES-GCM key wrapper (`LocalKms`).
- **Compression:** GZip only.
- **Dependencies:** the pyproject version floors are lower than 15 §1.
- **Dockerfile:** `ARG WITH_NODE` is not added yet.
- **Database role:** `app_migrator` is created by `scripts/init_local_db.sql`, not by a migration.
- **Exam queue:** refusing the memory queue backend is mapped to `EXAM_QUEUE_BACKEND`.

### Storage
- **Uploads:** presigned POST instead of PUT, because only POST can enforce `content-length-range`.
- **Profile photos:** limited to ≤ 2 MiB, JPEG or PNG only (spec D).

### Database
- **Deferred foreign keys:** the FKs from `platform.dead_jobs.resolved_by` and `platform.runtime_config.updated_by` to `identity.users` are added in `b01_06`, together with the users table.
- **Outbox fillfactor:** `platform.outbox` has no fillfactor, because PostgreSQL rejects storage parameters on a partitioned parent.
- **Partitions:**
  - Maintained by SECURITY DEFINER functions (`platform.create_range_partitions`, `platform.drop_partitions_before`), so the `app_rw` maintenance job needs no DDL rights.
  - Each child partition copies the parent's `app_rw` grants.
  - `create_range_partitions(…, ahead)` creates today plus `ahead` periods.
- **Daily template rebuild:** the test template database is rebuilt daily (today's date is part of its fingerprint), so the partitions it was migrated with stay current.

### Authorization and audit
- **Actor placement:** `Actor`, `can`/`require` and the `current_actor`/`admin_actor`/`staff_permission` dependencies live in `core/security` instead of `auth/contracts`. This follows 04 §4 R-03, so OPS stays a leaf: authorization reads token claims plus the `auth:grants:{user_id}` cache (60 s), and AUTH registers the DB loader in step 9. Without a loader there are no grants, so every check fails closed.
- **Revocation when Redis is down:** the `revoked_sess:{sid}` check fails closed for admin tokens and fails open, with a warning, for `aud=api`. Exposure is bounded by the 15-minute access-token lifetime.
- **Admin MFA:** admin tokens must carry `sso=true` and an `amr` containing one of `mfa`, `otp`, `hwk`, `swk`; otherwise the response is `403 mfa_required`.
- **Pagination:** the helper is in `core/pagination.py`, not `shared/`, because `shared` sits below `core` in the layer contract and the cursor errors use `core.errors`.
- **Audit log grants:** `app_rw` has SELECT and INSERT only (UPDATE, DELETE and TRUNCATE are revoked), and partitions inherit that. The SQL drop function refuses audit partitions younger than 36 months. Maintenance creates audit partitions 3 months ahead but never drops them; dropping waits for the B9 archive job.
- **Audit content:**
  - `before` and `after` store only the changed fields.
  - Keys with phone or email in the name become `{"hash": keyed_hash}`; other sensitive keys become `"[redacted]"`.
  - A reason is required when the action's last segment is `grant`, `refund`, `extend` or `invalidate`.
  - `ip_hash` is the keyed hash of `CF-Connecting-IP`, or of the peer address when that header is absent.
- **Audit search:** defaults to the last 30 days, allows at most 93 days per query, and pages by a keyset on `(occurred_at, id)`, newest first.

### Entry points
- **Worker process:** `workers` runs three loops on one stop event (SIGTERM and SIGINT set it): the job worker, the outbox relay (on by default; `--no-relay` turns it off) and the periodic scheduler, which ticks every 30 s and relies on `dedupe_key`, so running several schedulers is safe. The relay uses `DATABASE_URL`; in deployment that must be the direct, non-PgBouncer URL (R-17).
- **`--check` scope:** `workers --check` validates the settings, the queue names and that every periodic job has a handler, and pings Postgres and Redis. `exam-consumers --check` validates the settings and the SQS URL shape (`https://<host>/<account>/<queue>`); it does not call SQS.
- **exam-consumers:** a skeleton until B5. It boots, logs and waits for SIGTERM.
- **Shared boot code:** start-up shared by every deployable is in `entrypoints/boot.py`, which does not import the DB, so exam-ingest can use it. The DB-backed start-up for api, ai-gateway and workers is in `entrypoints/stack.py`. A subprocess test checks that the ingest app loads no SQLAlchemy, asyncpg, Alembic or `core.db`.
- **Docker and Compose:** per-deployable Docker commands and Compose services are left to step 13; the Dockerfile still defaults to the API.

### SMS (PLAN)
- **Revision order:** `b01_11_notify_sms` revises `b01_05` and lands before AUTH, because SMS has no identity dependency and AUTH's OTP flow needs it. The AUTH revisions `b01_06`–`b01_10` will chain after `b01_11`, so the order is b01_01..05, b01_11, b01_06..10, b01_12.
- **`fake_sent` status:** added to the `sms_messages.status` CHECK (01 lists queued/sent/delivered/failed; 05's risk table names `fake_sent`). Numbers in the reserved test block (`+8801700000000`–`+8801700009999`) never reach a gateway; they are stored as `fake_sent` with provider `test_block`.
- **Job payload:** holds the message id, its partition date and the rendered body encrypted with the field cipher. The jobs table never holds the phone or an OTP in plain text.
- **Idempotency of `plan.sms.send`:** a row lock plus `status = 'queued'` instead of `processed_events`; a duplicate or retried job after a successful send is a no-op.
- **Attempts:** OTP and guardian OTP get priority 100 and 3 attempts (a code expires in 5 minutes); other purposes get priority 0 and 8 attempts.
- **Dead jobs:** NFR gained `DeadLetterAware(run, on_dead)`. When a job goes dead the worker calls `on_dead` in a new transaction; for SMS it marks the message `failed` with the last error. A failing hook is logged and never blocks dead-lettering.
- **Templates:** `{placeholder}` rendering; `int` params become Bangla digits for `bn`, strings (OTP codes) stay ASCII so autofill works. Segments follow GSM 03.38 (160/153 for GSM-7, extension characters count twice; 70/67 UTF-16 units otherwise). The seeded OTP bodies are 2 segments in Bangla and 1 in English, with no links. A message over 10 segments is refused. Template bodies are cached in-process for 60 s.
- **HTTP gateway:** generic `POST SMS_API_URL` with a bearer key and `{to, sender_id, message}`; the vendor mapping waits for the vendor choice. Calls go through the `sms_gateway` circuit breaker; errors never include the phone or body. The fake gateway logs the body only when `APP_ENV` is local or test.
- **Template channels:** the `notify.templates.channel` CHECK is `sms`, `push`, `inbox` per 01.

### Telemetry
- **No exporter:** `core/telemetry.py` installs SDK tracer and meter providers without an exporter. The OTLP exporter package comes with the deployment work (19).
- **Coverage setting:** coverage now runs with `concurrency = ["thread", "greenlet"]`; without it, lines after SQLAlchemy async awaits reached through the ASGI app are not counted.

### Behaviour notes
- **Outbox relay:** one Parquet object per batch of ≤ 1,000 events. Object keys are deterministic (`events/date=…/hour=…/relay-<first_id>.parquet`), so a rerun overwrites the object instead of adding a duplicate. Each consumer gets one job per ≤ 500 matching events.
- **Idempotency:**
  - When a response is larger than 64 KiB and has a `resource_id`, only the id is stored; a replay re-reads the resource through the route's `reread` hook.
  - If Redis is down, the in-flight lock fails open.
- **Runtime config:**
  - `load_all` ends the read-only transaction it opened, so callers can still `session.begin()` afterwards.
  - The public `GET /v1/config/client` route is rate-limited on the `read` tier, keyed by client IP.

### Spec inconsistencies found (to resolve with the spec owner)
- **SMS revision name:** 05 names the SMS migration `b01_11` while 03 gives `b01_11` to COM and `b01_12` to SMS; 05's names are used (SMS `b01_11`, COM `b01_12`).
- **SMS status:** 01 has no `fake_sent` status, but 05's risk table relies on it.
- **OTP purpose:** the CHECK on otp purpose needs `step_up`.
- **Permission codes:** `moderation`, `privacy` and `curriculum` fail the permission-code regex.
- **Profile class level:** `admission`/`job` values conflict with the CHECK on 6–12.
- **Naming:** restriction scope names and report `target_type` values differ between the API spec and the DB spec.
- **Meta deletion:** the Meta data-deletion callback uses `identity.data_requests`.
- **HIBP:** HIBP fail-open is a B8 item.

## Proposed additions
None so far.

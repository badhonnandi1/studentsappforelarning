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
| 6–13 | OPS audit, entry points, SMS, AUTH, social, staff SSO, COM, seeds, hardening | pending |

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
- **OTP purpose:** the CHECK on otp purpose needs `step_up`.
- **Permission codes:** `moderation`, `privacy` and `curriculum` fail the permission-code regex.
- **Profile class level:** `admission`/`job` values conflict with the CHECK on 6–12.
- **Naming:** restriction scope names and report `target_type` values differ between the API spec and the DB spec.
- **Meta deletion:** the Meta data-deletion callback uses `identity.data_requests`.
- **HIBP:** HIBP fail-open is a B8 item.

## Proposed additions
None so far.

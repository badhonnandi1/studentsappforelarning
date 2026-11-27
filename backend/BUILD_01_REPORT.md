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
| 9 | AUTH core (in parts): `b01_06`–`b01_10` schema and seeds; OTP sign-in, tokens, sessions, `/v1/me`; RBAC and role grants; profile, reference lists, presign, photo | in progress |
| 10–13 | Social, staff SSO, COM, seeds, hardening | pending |

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

### Identity schema (AUTH, `b01_06`–`b01_10`)
- **OTP purpose:** the `otp_challenges.purpose` CHECK adds `step_up` (R-25 needs it; 01 lists three purposes).
- **Permission codes:** the CHECK is `^[a-z_]+(\.[a-z_]+)*$`, so the single-word codes that 05 §C.6 and 14 use (`moderation`, `privacy`, `curriculum`) are valid; 01's regex required a dot.
- **Class level:** `profiles.class_level` is `BETWEEN 6 AND 14`; 13 stores `admission` and 14 stores `job` (the API speaks the words). 01's CHECK stopped at 12.
- **Device sessions:** added `audience` (`api`/`admin`; staff sessions refresh for 12 h and mint `aud=admin`), `sso` in the `sign_in_method` CHECK, `restricted_until` (the 72 h restricted mode, R-25) and a partial unique `(user_id, device_id, audience) WHERE revoked_at IS NULL` (one live session per device).
- **Global grants:** the active-grant unique index uses `NULLS NOT DISTINCT`, so a second active global grant of the same role is refused (with plain NULLs it would not be).
- **OTP index:** `(phone_hash, created_at)` ascending; a B-tree serves the "latest first" scan backwards and avoids an expression index that `alembic check` cannot compare.
- **Role → permission seed (default until the content builds refine it):** `content_author` = content.read, content.author; `reviewer` = content.read, content.verify, content.triage; `ops_admin` = user.read, user.write, audit.read, ops.config, moderation, privacy; `super_admin` = all. `student`, `parent`, `teacher` and `institution_admin` have no B1 permissions. Staff roles (`is_staff`) are content_author, reviewer, ops_admin and super_admin.
- **Seed copy:** `b01_08` holds a frozen copy of the roles and permissions; `tests/contract/test_rbac_seed.py` checks it against `auth/internal/permissions.py`.
- **Model loading:** `start_stack` calls `registry.load_models()`, because NFR tables now have FKs to `identity.users`.
- **OTP retention:** `otp_challenges` rows are purged after 30 days (01 §4.2); the step 5 rule said 24 hours.
- **Round trip:** a test runs `downgrade base` → `upgrade head` → `alembic check` on a copy of the template.

### OTP sign-in, tokens and sessions (AUTH, step 9 part 2)
- **Schema additions:**
  - `otp_challenges.phone_enc` is encrypted with context `identity.otp_challenges.phone`, because verify receives only the challenge id and guardian consent needs the number.
  - `device_sessions.model` (≤ 64 chars).
  - Revoke reason `session_limit`, used when the session cap evicts the oldest session.
- **CAPTCHA:** Cloudflare Turnstile. `TURNSTILE_SECRET` and `OTP_CHALLENGE_URL` are required in deployed environments. Local and test environments accept the token `local-pass`. Play Integrity is not implemented in B1.
- **When a challenge is required:** when the number's challenges in the last hour have ≥ 3 failed attempts in total (SUM of `attempts`). The response is `403 challenge_required` with `details.challenge_url`.
- **Order of limits:** IP and device limits, then the CAPTCHA check, then the phone limit (3 per 15 min, 5 per day). A request refused for CAPTCHA does not spend the number's quota.
- **Device limit:** `otp_ip` gains a device rule of 10 per hour.
- **Rate-limit keys:** all are keyed hashes, so Redis holds no plain phone numbers, IPs or device ids.
- **OTP send behaviour:**
  - `resend_after_s` is 60.
  - A suspended number is refused with `403`.
  - Known and unknown numbers get the same `202` body.
  - Idempotency on the public send is deferred, because it has no user to key on.
- **Verify:**
  - A wrong code returns `401 invalid_code` with `details.attempts_left`. The attempt count commits even though the request fails.
  - The 6th attempt returns `429`. An expired or used code returns `410`.
  - A double verify of one challenge is serialised by a row lock: one sign-in, one `410` (concurrency test).
- **Pending sign-up:**
  - Redis `auth:pending_signup:{token}` (32-byte token, 15 min, `GETDEL` single use).
  - The phone in it is field-encrypted.
  - The DOB is checked before the token is spent: 1900-01-01 ≤ DOB < today (Dhaka date).
  - A number that signed up in the meantime gives `409`.
- **Refresh rotation:**
  - Opaque 32-byte tokens; only their SHA-256 is stored.
  - Each rotation issues a child in the same family.
  - Replaying a rotated token revokes the whole family and the device session (`token_reuse`). The audit action is `auth.refresh.reuse`, because the spec's `auth.refresh_reuse` fails the action regex.
  - `api` refresh slides 30 days. `admin` (staff) refresh keeps the first token's expiry, so it does not slide. Staff tokens re-mint `sso=true, amr=["mfa"]` on refresh.
- **Device sessions:**
  - Signing in again on the same device reuses the live session and revokes its old tokens.
  - When the cap is passed, the oldest session is revoked.
  - `/v1/me/sessions` lists only `api`-audience sessions.
  - Revoking a session that is not the caller's returns `404`.
  - After commit, `revoked_sess:{sid}` is set, so access tokens fail on their next request.
- **Consent state in `/v1/me`:** `granted`, `missing` or `not_required`.
- **Event:** `user.signed_in` (v1) is registered in `auth/contracts/events.py`. Its payload holds the session id, method, platform and created flag, and no PII.
- **Module layout:** `refresh.py` and `summary.py` are split out of `tokens.py` to avoid an import cycle.
- **Lock ordering:** refresh locks token → session, while signing in again locks session → tokens. A deadlock between a refresh and a sign-in on the same device is possible but rare; PostgreSQL aborts one of the two, and the client retries.
- **Deferred:**
  - Display-name moderation (COM, step 11).
  - Rejecting suspended users in `current_actor`; suspension revokes their sessions instead (step 11).
  - Dormant-account and step-up rules (step 10).

### RBAC and role grants (AUTH, step 9 part 3)
- **Grants loader:** each module may expose `startup()`. `registry.run_startup()` calls these from `start_stack` after the engine exists. AUTH's `startup()` registers the DB loader: active grants joined to `role_permissions`, giving one `Grant` per (permission, scope). Grants are cached for 60 s in `auth:grants:{user_id}`.
- **"Above your own":** a granter may grant or revoke a role only when every permission of that role is among the granter's own permissions in that scope. Only `super_admin` may grant or revoke `super_admin`. Otherwise the response is `403 role_above_own`. The route also requires `role.grant` in the grant's scope; by the seed only `super_admin` holds it.
- **Grant rules:**
  - An unknown role returns `422 unknown_role`. An unknown user returns `404`. An active duplicate returns `409`.
  - The user row is locked, so concurrent grants to one user are serialised.
  - `scope_id` must be set exactly when the scope is `subject` or `tenant` (422 otherwise).
  - `reason` is required (3–500 characters, the same as runtime config).
  - Audit actions are `auth.role.grant` (reason required) and `auth.role.revoke`.
- **Revoking:**
  - Revoking invalidates the grants cache. If Redis is down, a warning is logged and the 60 s TTL bounds the staleness.
  - Revoking a staff role also ends the user's live `admin` sessions (reason `admin`), so a stale `roles` claim cannot keep the super-admin bypass alive for the rest of the access token's lifetime.
  - Revoking an already revoked grant returns `404`.
- **Super-admin bypass:** recorded as a structured security log event (`rbac_super_admin_bypass`), not as an `audit_log` row. `can()` is a synchronous core check with no transaction. Every write a super admin makes is still audited by the write's own `audited()` row, which carries the actor's roles.
- **Roles claim after a grant:** a new grant shows in permission checks within 60 s (cache). The `roles` claim in the access token updates on the next refresh.

### Profile, reference lists and uploads (AUTH and NFR, step 9 part 4)
- **Class level:**
  - The API accepts 6–12 or `admission`/`job` (stored as 13 and 14).
  - Classes 9–12 need `science`, `business` or `humanities`. Other classes take no group, or `general`.
- **Other profile fields:**
  - `exam_year` runs from the current Dhaka year to that year + 6.
  - An unknown or inactive institution returns `404`.
  - An unknown district returns `422`. The upazila must belong to the chosen district.
  - `board_code` is free text in `^[a-z_]{2,20}$` until the board list exists (B3).
  - Each 422 carries `details.field`.
- **Date of birth:** it is always set at sign-up (R-24). On `PUT /v1/me/profile` the same value is accepted, and a different one gets `422 dob_locked` ("contact support").
- **Institution search:**
  - Trigram similarity on `name_en` and `name_bn`, plus a substring match, best match first.
  - Inactive institutions are hidden.
  - At least one of `q` (≥ 2 characters) and `district_id` is required.
  - It returns one page of at most 50 results; `next_cursor` is always null, because a similarity order has no stable keyset.
- **Districts list:** returns `Cache-Control: public, max-age=86400`. Both reference routes are on the `read` tier, keyed by IP.
- **Presign:**
  - `GET /v1/uploads/{purpose}/presign` is in `nfr/internal/routes/uploads.py`.
  - Only `profile_photo` is enabled in B1; other purposes and declared sizes over the limit return `422`.
  - It uses the `upload` tier per user (30 per hour).
  - `bytes` is checked against the purpose limit, and the POST policy enforces the limit again at S3.
- **Photo checks (B1):**
  - The key must be the caller's own `profile_photo/YYYY/MM/{user_id}/<uuid>.(jpg|png)`.
  - The object is read from S3 (≤ 2 MiB). Its magic bytes must match the extension, and both dimensions must be 64–4096 px. The size range is our choice; the spec says only "dimension checks".
  - Otherwise the response is `422 invalid_upload`.
  - Headers are parsed by `shared/image_header.py` (PNG and JPEG only, no imaging dependency).
  - A passing photo is stored as `pending` and is not public.
- **Shared helpers:**
  - `core.security.deps.user_tier(tier)` is the current actor, rate-limited per user. It replaces the per-module helper.
  - `core.storage.get_storage()` is a dependency, so tests can override it.
  - `summary.signed_in_user()` is shared by the `/v1/me*` services.
- **Moved to step 10:** `POST /v1/me/phone` needs the step-up OTP (R-25), which step 10 builds.

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
- **OTP purpose:** the CHECK on otp purpose needs `step_up` (resolved as above).
- **Permission codes:** `moderation`, `privacy` and `curriculum` fail 01's permission-code regex (resolved as above).
- **Profile class level:** `admission`/`job` values conflict with the CHECK on 6–12 (resolved as above).
- **Naming:** restriction scope names and report `target_type` values differ between the API spec and the DB spec.
- **Meta deletion:** the Meta data-deletion callback uses `identity.data_requests`.
- **HIBP:** HIBP fail-open is a B8 item.

## Proposed additions
None so far.

# Build 1 report

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
| 9 | AUTH core (in parts): `b01_06`–`b01_10` schema and seeds; OTP sign-in, tokens, sessions, `/v1/me`; RBAC and role grants; profile, reference lists, presign, photo; privacy, guardian consent, consent documents, stale-session purge | done |
| 10 | AUTH social (in parts): providers, nonce, social sign-in (part 1); step-up, dormant rule, identities, phone change (part 2); Meta callbacks (part 3) | done |
| 10a | Staff SSO (R-07): OIDC client, start/callback, admin-audience checks | done |
| 11 | COM moderation (in parts): folding, `moderate()`, terms admin, display-name checks (part 1); reports, restrictions, bans (part 2) | done |
| 12 | Seeds and smoke: `seed_reference`, `seed_dev`, end-to-end API test | done |
| 13 | Hardening, README, OpenAPI snapshot (part 1); acceptance tests, social sign-in race fix, deployable smoke, load script (part 2) | done |

## Acceptance criteria (05 §F.1)

Local results on 2026-11-28: `scripts/check.sh` green, **568 tests passed**, **99.15% branch coverage** overall, and every one of the 51 critical-path files at ≥ 95% (lowest 95.2%).

| # | Criterion | Status |
|---|---|---|
| 1 | `check.sh` passes locally and in CI | Locally: met. CI: the workflow is in place and has not yet run on GitHub. |
| 2 | Coverage ≥ 85% overall, ≥ 95% on critical paths | Met (99.15%; lowest critical file 95.2%). |
| 3 | All 5 deployables start in Docker | Met locally with `scripts/smoke_deployables.sh`: `/readyz` 200 ×3, `--check` exit 0 ×2. |
| 4 | Sign-up and sign-in by OTP, Google, Facebook; linking matrix | Met in tests, with the fake JWKS and Graph API. The real Google test account and the Meta test user on staging are manual checks (§F.5). |
| 5 | Refresh reuse revokes within one request; logout blocks the access token | Met (`test_tokens.py`, `test_end_to_end.py`). |
| 6 | 1,000 jobs once over 8 workers; killed worker's jobs complete after lease | Met (`tests/concurrency/test_job_claim.py`). |
| 7 | 10,000 events relayed with zero loss and zero duplicates on replay | Met (`tests/concurrency/test_relay_volume.py`). |
| 8 | Every B1 admin write is audited | Met (`test_admin_writes_audited.py`, `test_authz_matrix.py`, `test_audited.py`). |
| 9 | No plain-text PII in the database | Met for the PII flows (`tests/security/test_no_plaintext_pii.py`). The scan runs inside its own test, not after the whole suite, because each test rolls back. |
| 10 | Migrations round-trip on PG17; staging behind PgBouncer passes the API suite | Round trip: met (the migration tests and the CI migration job). PgBouncer transaction mode on staging: not done, because no staging environment exists yet. |

Not done in B1 and outside this build's reach: the CI run on GitHub, the staging items (#4 real providers, #10 PgBouncer), the §F.5 manual checklist and the k6 run.

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

### Privacy, guardian consent and consent documents (AUTH, step 9 part 5)
- **Consent documents:**
  - v1 is `2026-11-v1` (`guardian_consent`, bn and en), seeded in `b01_10` with the SHA-256 of each body.
  - The bodies are static files in `auth/internal/consent_docs/`; `tests/contract/test_consent_seed.py` checks each file against its hash.
  - The text is a **draft placeholder, clearly marked, pending the legal decision D4**. A changed text ships as a new version in a new revision.
  - `GET /v1/consent-documents/{version}?lang=` is public, `read` tier per IP, with `Cache-Control: public, max-age=86400`; `lang` defaults to `bn`.
- **Guardian consent start:**
  - T-otp per IP and per guardian number.
  - A guardian number equal to the user's own gets `422 same_phone`.
  - An existing active consent gets `409 consent_active`.
  - A version other than the latest published one gets `422 consent_version_outdated`, with `details.latest`.
  - **Our addition:** an adult (18 or over on the Dhaka date) gets `409 consent_not_required`. The spec does not cover this case.
- **Binding a challenge to its user:** `otp_challenges` has no user column, so start keeps `{user_id, relation, version}` in Redis under `auth:guardian:{challenge_id}`, for the code's lifetime plus 10 minutes. It holds no phone. If Redis is down, start and confirm return `503`.
- **Guardian consent confirm:**
  - The binding must exist and belong to the caller; otherwise `401 invalid_code`.
  - The user row is locked, so two challenges cannot both record a consent.
  - It consumes the OTP (wrong code `401`, used or expired `410`, too many attempts `429`) and inserts `guardian_consents`.
  - The guardian phone is envelope-encrypted (context `identity.guardian_consents.guardian_phone`) and stored with its keyed hash; the relation goes in `scope`.
  - It writes the audit row `auth.guardian_consent.record`, all in one transaction.
  - The consent state is computed (an active, not-withdrawn row), not stored on `users`. A withdrawn consent makes `needs_consent` true again. B1 has no withdrawal route; withdrawal is done by support or B8 PAR.
- **Privacy:**
  - Defaults: `profile_private = true`, `leaderboard_visible = true`.
  - Hiding oneself sets `opt_out_by = self`; showing again clears it.
  - While `opt_out_by = guardian`, the user cannot turn `leaderboard_visible` back on (`403 forbidden`); other fields can still change.
  - Privacy changes are not audited (they are the user's own settings).
- **`auth.sessions.purge_stale`:**
  - Runs daily at 03:00 Dhaka on `maintenance`.
  - Sessions with no activity for 90 days, and their refresh tokens, are marked revoked with the new reason **`inactive`** (added to the `b01_07` CHECK and to `REVOKE_REASONS`). Nothing is deleted.
  - It works in batches of 5000 (at most 20 per run) with `SKIP LOCKED`.
- **Periodic jobs from modules:** a module may expose `periodic_jobs()`. The worker entrypoint registers them with the NFR scheduler (`register_periodic_jobs`), because the module-edge map does not allow the registry to import NFR.

### Social sign-in (AUTH, step 10 part 1)
- **Providers:**
  - Each provider sits behind a `SocialProvider` protocol (`verify(token, nonce)` returns `VerifiedIdentity`).
  - Each provider call runs through a circuit breaker (`social_google`, `social_facebook`) with a 3 s timeout.
  - A 5xx response, a transport error, an open breaker or Redis down gives `503 unavailable` with `details.fallback = "phone_otp"`.
  - A token that fails verification gives `401 invalid_provider_token`.
  - A disabled provider gives `404`, both for the nonce and for sign-in.
- **JWKS cache:**
  - Redis `jwks:{sha256(url)[:16]}`, with the TTL taken from `Cache-Control: max-age` (clamped to 5 min–24 h; 1 h if there is none).
  - An unknown `kid` refetches the keys at most once per 30 s (`…:refetch`), so random kids cannot make us hammer the provider.
  - If Redis cannot be reached for the cache, each request fetches the keys itself.
- **Google:**
  - The ID token must be RS256 (any other `alg` is rejected).
  - It must have `iss` ∈ {`accounts.google.com`, `https://accounts.google.com`}, `aud` among `GOOGLE_CLIENT_IDS`, and `exp`, `iat`, `sub` present.
  - `iat` may be at most 60 s ahead, and the nonce is compared in constant time.
  - The email is lower-cased and trimmed.
- **Facebook:**
  - A classic access token goes through `debug_token` with the app token. The checks are `is_valid`, `app_id` equal to ours, `user_id`, and `expires_at` (0, or in the future).
  - Then `/me?fields=id,name,email` is called with `appsecret_proof`, and its `id` must equal `debug_token`'s `user_id`.
  - A Limited Login (iOS) OIDC token is verified against Facebook's JWKS: `iss` `https://www.facebook.com`, `aud` = app id, plus the nonce.
  - Facebook emails are always treated as unverified, so they are never auto-linked.
  - **Deviation:** a classic access token cannot carry our nonce. For that path the nonce is only consumed (single use, bound to the provider), not matched against the token.
  - Tokens and the app secret are never logged, and no provider access token is stored.
- **Nonce:**
  - `POST /v1/auth/social/nonce {provider}` uses the auth tier.
  - It returns 32 random bytes (URL-safe), stored at `nonce:social:{nonce}` with the provider name for 5 minutes.
  - Sign-in takes the nonce with `GETDEL`. An unknown, reused or other-provider nonce gives `401 invalid_nonce`. Redis down gives `503`.
- **`POST /v1/auth/social/{provider}` (§C.5):**
  - A date of birth, if sent, is validated before the nonce is spent.
  - An active identity signs in: it updates `last_login_at`; suspended or deleted accounts are refused as for OTP.
  - With no identity yet, Google with `email_verified` and an email equal to an account's verified email links to that account. This writes the audit row `auth.identity_autolinked` and sets `linked = true`.
  - The autolink is skipped if that account already has a different active Google identity.
  - Otherwise, with no date of birth, nothing is created and the response is `needs_profile` with a pending sign-up token. The verified identity is stored encrypted in Redis (context `auth.pending_signup.identity`), for 15 minutes, single use. `/v1/auth/sign-up/complete` now accepts these tokens as well as phone ones.
  - Otherwise the user and the identity are created in one transaction (`created = true`).
  - Facebook under 13 (Dhaka date) gets `403 age_restricted` before anything is created. The same check runs on sign-in for an existing account.
- **Account creation:**
  - Account creation now lives in one place (`services/accounts.py`), shared by phone and social sign-up.
  - It honours **`kill.registrations`**: new accounts are refused with `503 kill_switch`, while existing users still sign in. The spec lists the key but does not say where it is enforced.
  - A verified Google email is stored on the new user (encrypted, keyed hash, `email_verified_at`) unless another account already has that email; it is never moved.
  - The identity's email, if any, is stored encrypted with its keyed hash. Unlinked identity rows are reused on relink, because `(provider, provider_subject)` stays unique after unlinking.

### Step-up, dormant rule, linked identities and phone change (AUTH, step 10 part 2)
- **Step-up OTP (R-25):**
  - **Our addition:** `POST /v1/auth/step-up/send {action}` sends the OTP to the account's verified phone. It returns 202 with a challenge and applies the T-otp limits. The spec defines only the verify call and does not say how the code is requested.
  - A challenge belongs to the caller when its phone hash equals the caller's (numbers are unique), so no Redis binding is needed.
  - `POST /v1/auth/step-up` returns a token valid for 10 minutes. It is bound to the user, the session and the action, and stored in Redis only as its SHA-256 (`auth:step_up:{hash}`).
  - The token is **single use**: it is deleted after the action commits. A missing, wrong-action, other-session or spent token gives `403 step_up_required`. Redis down gives `503`.
  - An account with no phone gets `403 phone_required`, both for the send call and for unlink.
- **Dormant and new-device rule (R-25):**
  - It applies to phone OTP sign-in when the account's `last_seen_at` is more than 180 days ago and the `device_id` has never had a session for the account (sessions are never deleted).
  - With a linked Google or Facebook identity, OTP verify returns `200 {status: "second_factor_required", providers}` and starts no session. The OTP is spent, and the client signs in with the provider.
  - Without one, the session starts with `device_sessions.restricted_until = now + 72 h`, and `SignInOut.restricted_until` reports it.
  - A restricted session gets `403 restricted_session` for unlink and phone change. Payments (B3+) must check it too; the check is `step_up.ensure_unrestricted`.
  - Signing in again on the same device does not clear the restriction.
- **Linking:**
  - `POST /v1/me/identities/{provider}` verifies the token and nonce like sign-in.
  - It returns `409 identity_in_use` if another account holds the identity, `409 conflict` if the caller already has that provider, and `403 age_restricted` for Facebook under 13.
  - It writes the audit row `auth.identity.link`. A previously unlinked row for the same subject is reused.
- **Unlinking:**
  - The checks run in this order: phone required, unrestricted session, step-up token (`unlink`), `404` if the provider is not linked, then the last-method guard.
  - Because a verified phone is required, the last-method guard (`409 last_sign_in_method`) cannot trigger in B1. It is kept for B8 passwords.
  - The row is kept with `unlinked_at` and `unlink_reason = user`, and the audit row is `auth.identity.unlink`.
  - `GET /v1/me/identities` masks emails as `k***@domain`.
- **Phone change (`POST /v1/me/phone`):**
  - Step 1 `{phone}` needs a step-up token (`phone_change`) and an unrestricted session. **Deviation:** an account adding its first number needs no step-up, because there is no number to confirm with.
  - A number held by another account gives `409 conflict` (support merges by hand). Your own number gives `422 same_phone`.
  - The OTP (`purpose = phone_change`) goes to the new number. The challenge is bound to the caller in Redis (`auth:phone_change:{challenge_id}`, holding the user id only), and the step-up token is spent.
  - Step 2 `{challenge_id, code}` re-checks the number, stores it encrypted with its keyed hash, and writes the audit row `auth.phone.change`, in one transaction.
  - Other sessions are not revoked on a phone change (the spec does not ask for it; see Proposed additions).
- **Deletion step-up:** the `deletion` and `guardian_change` actions are accepted, but B1 has no user deletion-request or guardian-change route (§D lists none). The 05 test line "deletion without `X-Step-Up-Token` → 403" therefore waits for the build that adds the route.
- **Module layout:** the dormant rule is in `services/dormant.py`, not `step_up.py` as 05 §B lists, to avoid an import cycle with `otp_verify`.

### Meta callbacks (AUTH, step 10 part 3)
- **`signed_request`:**
  - The signature (base64url HMAC-SHA256 of the encoded payload, with the app secret) is compared in constant time **before** the payload is parsed.
  - The payload must be a JSON object with `user_id` and `algorithm = HMAC-SHA256`. Any failure is `400 bad_request` with no detail.
  - With Facebook disabled, the callbacks return `404`.
  - Both callbacks use the auth tier per IP; the status page uses the read tier per IP.
- **Data deletion:**
  - The Facebook identity is unlinked (`unlink_reason = data_deletion`) and an `identity.data_requests` row is opened: `kind = deletion`, `requested_via = facebook_callback`, and a random 16-byte confirmation code.
  - The audit row is `auth.identity.data_deletion`, with actor kind `provider`.
  - A repeated callback while a request is still open returns the same code.
  - Carrying out the deletion stays support-driven until B6.
  - **Deviation:** for a Facebook user we have never seen, the callback still returns 200 with a code, because Meta requires one. No row can exist (`data_requests.user_id` is NOT NULL), so that code's status page is `404`.
- **Status:** `GET /v1/auth/social/facebook/deletion-status/{code}` returns `received` (for `open`, `in_progress` or `rejected`) or `completed`, with `completed_at`.
- **Deauthorise:** unlinks the identity (`deauthorized`), writes the audit row `auth.identity.deauthorize`, and returns `{}`.
- **New setting `PUBLIC_API_URL`:** the base of the status URL given to Meta. It must be https when Facebook is enabled in prod or staging.

### Staff SSO (AUTH, step 10a)
- **Shared JWKS verifier:** the JWKS cache, the ID-token checks and the circuit-broken HTTP call moved from `auth/internal/providers/jwks.py` to `core/security/jwks.py`, so that the core OIDC client can share them.
  - Core raises `InvalidTokenError` and `IdpUnavailableError`.
  - The provider module is now a thin adapter that maps them to `401 invalid_provider_token` or to `503` with the phone-OTP fallback. Behaviour, cache keys and breaker names (`social_{provider}`) are unchanged.
- **`core/security/oidc.py`:**
  - Authorisation code flow with PKCE S256, `state` and `nonce`. The client authenticates at the token endpoint with `client_secret_post`.
  - The discovery document is cached in Redis for 1 h, and its `issuer` must match exactly.
  - For an ID token with several audiences, `azp` must equal our client id.
  - The access and refresh tokens the IdP returns are discarded.
- **`/v1/admin/auth/sso/start?redirect_uri`:**
  - The redirect URI must exactly match an entry in `STAFF_OIDC_REDIRECT_URIS`; otherwise `400`.
  - `{nonce, code_verifier, redirect_uri}` is stored in Redis for 10 min under the SHA-256 of a random 32-byte state.
  - Returns `302` with `Cache-Control: no-store`.
  - If Redis or the IdP is down, it returns `503`. If no client id is configured, it returns `404`.
- **`/v1/admin/auth/sso/callback?code&state`:**
  - The admin web app receives the IdP redirect and forwards `code` and `state`. The state is taken once (`GETDEL`); an unknown or reused state is `400`.
  - The checks run in this order:
    1. An MFA method in `amr` (`mfa`, `otp`, `hwk`, `swk`); otherwise `403 mfa_required`.
    2. `email_verified = true`, an email domain in `STAFF_OIDC_ALLOWED_DOMAINS` (case-insensitive) and, when present, `hd` equal to that domain; otherwise `403 forbidden`.
    3. An existing user whose `email_hash` matches, with a verified email and an active staff role; otherwise `403 forbidden`.
  - A failed code exchange or a bad ID token is `401 invalid_provider_token`. An unreachable IdP is `503`.
  - The response is an admin `TokenPair` (`aud=admin`, `sso=true`, `amr=["mfa"]`, a 12 h refresh that does not slide).
  - Audit: `auth.staff_sign_in` (actor kind `staff`), recording the IdP's `amr`, the domain and the staff roles. The email is not recorded.
- **Device:** the callback uses the `X-Device-Id` header when sent. Otherwise each sign-in opens its own admin session (`sso-<uuid7>`, platform `web`).
- **Admin-audience test:** a table-driven test lists every `/v1/admin/*` operation from the OpenAPI schema (except the two SSO routes). Each one must reject a user token (`401`) and admin tokens without `sso` or without an MFA `amr` (`403`).
- **Deferred:** the "seed_dev tokens refused when `APP_ENV=prod`" check is tested with `scripts/seed_dev.py` in step 12. The settings validator already refuses `DEV_STAFF_TOKENS` in prod and staging.
- **Risk (needs a decision before staff use):** Google's ID tokens normally carry no `amr` claim, even when 2-Step Verification is enforced for the Workspace. With the default issuer, the `amr` rule as specified would refuse every staff sign-in. Options:
  - an IdP or broker that emits `amr` (for example Okta, Entra ID or Keycloak in front of Workspace);
  - a documented exception that trusts Workspace-enforced 2SV for the allowed domains.

  The code follows the spec (MFA `amr` required); nothing was relaxed.

### Moderation (COM, step 11)
- **CHECK lists (`b01_12`):** where 05's API and 01's CHECKs differ, the CHECK takes both. Report `target_type` adds `profile_photo` and `other`; restriction `scope` adds `profile` (the API's `all` is stored as `global`); decision `context` adds `content_report`, because report text is moderated.
- **Folding bug fixed in `shared/bangla_text.py`:** the punctuation regex `[^\w\s]` treated Bangla vowel signs and the hasanta as punctuation (Python's `\w` does not match combining marks), so `fold("সয়তান")` gave `"সযত ন"`. The Bangla block now counts as word characters; `tests/shared/test_bangla_text.py` covers it.
- **Two fold families:** `fold` (Bangla letters plus Banglish spelling rules, which collapse doubled letters) would make the English term "ass" equal to "as". English terms use the new `fold_latin` (look-alikes, punctuation, runs of 3+ letters); `bn` and `banglish` terms use `fold`. The text is folded both ways and each family is matched against its own terms.
- **Matching:** whole tokens and n-grams, so a clean word that contains a term ("class") does not match. Runs of single letters are joined first ("b a d w o r d"). Severity 1 is `flag`, 2 is `block`, 3 is `block` with `alert=true`. Only flag and block are logged in `moderation_decisions`; no classifier runs in B1 (`classifier_score` stays null).
- **Term cache:** active terms are cached per process for 5 minutes. An admin write drops the cache in that process only; other processes pick up the change within 5 minutes.
- **Decision log on a block:** when `moderate` is called outside a transaction it commits its own log row, so a block is recorded even though the caller refuses the write.
- **Display names:** user-entered names are checked on `PATCH /v1/me` and on `POST /v1/auth/sign-up/complete`, where a block is `422 moderation_blocked`. Sign-up checks the name before spending the pending token, so the user can retry. Provider-supplied names are not moderated in B1; they are never shown publicly until the user sets a display name. `first_name`/`last_name` are private and not moderated.
- **Restrictions:**
  - The API's scope `all` is stored as `global`, which covers every scope.
  - A ban of any scope ends all the user's sessions (reason `admin`, refresh tokens revoked, access tokens refused through the Redis revocation list). Only a global ban also refuses sign-in, with `403 account_banned` checked in `sign_in.start_session`. A `community` or `profile` ban is "signed out once, may come back with limits".
  - COM does not import AUTH: AUTH registers a `SessionRevoker` (`BanRevoker`) in `auth.startup()`, and COM raises if none is registered.
  - A mute or ban in `community` (or `global`) refuses `POST /v1/reports` with `403 restricted`. A `profile` restriction refuses display-name changes on `PATCH /v1/me` with the same code; other fields still change.
  - `is_restricted` reads a 60 s Redis cache (`com:restrictions:{user_id}`). Every COM write drops it; with Redis down it reads Postgres.
  - Lifting sets `lifted_at`. It does not restore ended sessions; the user signs in again.
  - An unknown `user_id` is `404` (the FK violation is mapped). `ends_at` in the past is `422`.
- **Reports:**
  - Rate limit: a new `report` tier (20 per user per 86,400 s). Report text runs through `ensure_allowed` (context `content_report`); a block is `422 moderation_blocked`.
  - Creation is audited (`com.report.create`, actor kind user), so every COM write is in `audit_log`.
  - The admin queue pages oldest first (a work queue, matching the `(status, created_at)` index).
  - Resolve: there is no note column, so the note goes in the audit `reason` (and is the restriction's reason when one is applied). A resolved report is `409`. A restriction needs `decision=action_taken` and a report about a user (`user`, `display_name`, `profile_photo`, where `target_id` is the user id); post and `other` reports cannot carry one in B1 (`422 target_not_a_user`), because posts arrive in B2.
  - The resolution, the restriction and the idempotency record commit in one transaction.
- **Terms admin:** `severity` uses low/medium/high on the API (1/2/3 in the DB). A delete is soft (`is_active=false`), and adding the same term again reactivates the row. Every write is audited (`com.term.create`, `com.term.delete`).

### Seeds (step 12)
- **Data shipped:** `seed/districts.csv` holds all 64 districts, keyed by BBS district geocode, with Bangla and English names. Check it against the current BBS list before launch.
- **Data not shipped:** `upazilas.csv`, `institutions.csv` (BANBEIS, with EIIN) and `moderation_terms.csv` contain headers only. Making up ~495 upazilas, an EIIN list or a profanity list would put unverified data into production, so the data owner and the content team supply these files. `seed/README.md` documents the columns.
- **`seed_reference.py`:** checks every row of every file before writing anything; a bad row raises `SeedError` with the file and line. Districts and upazilas upsert on id. Institutions upsert on `uuid5(EIIN)`, so reruns update in place. Terms upsert on `(lang, term_folded)`, folded the way the admin route folds them.
- **`seed_dev.py`:**
  - Creates one super admin (`admin@example.com`), three students in the reserved test phone block, and one Google and one Facebook identity. All go through the real account code (`create_user`, `create_social_account`); no provider is called. Reruns reuse every row.
  - Prints an admin token from a real `sso` staff session.
  - Refuses with `DevOnlyError` unless `APP_ENV` is `local` or `test`. Settings has no `dev` value; `local` is the dev environment. Tests cover the refusal in staging and prod.
  - The script cannot mint a prod-valid token in any case: prod signing keys never exist outside the deployment.
- **End-to-end test:** `tests/modules/auth/test_end_to_end.py` covers OTP sign-up → profile (seeded district) → guardian consent → refresh → session revoke (access token refused, refresh refused).

### Hardening (step 13)
- **Already in place:** most of the hardening landed with step 2 (`core/http.py`, `core/middleware.py`): security headers, the CORS allow-list, body limits, and the prod settings validator. Step 13 closes the gaps that were left.
- **CORS:** `allow_headers` was `*`. It is now the exact list of request headers the API reads: `Authorization`, `Content-Type`, `Idempotency-Key`, `X-Device-Id`, `X-Step-Up-Token`, `X-Request-ID`, `traceparent`. Preflights are cached for 600 s. Credentials stay off because auth is by bearer token, not cookie. Tests cover a listed origin, an unlisted origin and an unlisted header.
- **`Cache-Control: no-store` (addition):** now the default on every API response. RFC 6749 §5.1 requires it for token responses, and it keeps personal data out of shared caches. Routes that serve public reference data set their own value first (`/v1/reference/*`, `/v1/config/client`). The docs pages are untouched.
- **Body limit bug fixed:** a chunked body with no `Content-Length` that went over the limit got FastAPI's `400` instead of `413`, because FastAPI catches the exception raised while it reads the body. The middleware now discards the app's reply and sends the `413` itself.
- **Log redaction:**
  - New sensitive keys: `appsecret`, `api_key`, `private_key`.
  - String values, the event text and rendered tracebacks are now also scanned, and Bangladesh mobile numbers (`+880…`, `880…` and `01…` forms) and email addresses are masked. This backs up the key rule. Callers still must not log PII.
  - Tests check that ids, hashes and years survive the scan.
- **Critical coverage:** the paths now match all the B1 groups in 15 §5. Added: `nfr/internal/services/{enqueue,publish}.py`, `nfr/internal/jobs/*`, and `ops/internal/services/audit*`. A test was added for the retention job skipping tables that later builds create.
- **OpenAPI snapshot:**
  - `scripts/export_openapi.py` writes `openapi.json`: 43 paths, built from default local settings so the output is the same on every machine.
  - `tests/contract/test_openapi_snapshot.py` fails when the committed file is stale, so CI catches drift in the existing test job.
- **`backend/README.md`:** covers how to run, test and lay out the code, the conventions, and the HTTP hardening.
- **Bug fixed: first social sign-in race.** Two parallel first sign-ins with one new identity both found no identity row and both inserted. The second hit a unique constraint and got a `500`. `create_social_account` now inserts in a savepoint. On `IntegrityError` it checks whether the identity now exists; if so it raises `RegistrationRaceError` (a `409 conflict`, "sign in instead"). `sign_in_with` retries once, and the retry is an ordinary sign-in to the winner's user, so the result is one user and two sessions. A parallel `sign-up/complete` with two pending tokens for one identity gets the `409`. An `IntegrityError` with no winning identity is re-raised unchanged.
- **Authorization matrix:** `tests/modules/auth/test_authz_matrix.py` classifies every route in the app (49 method/path pairs) as public, user, owned or staff, and fails when a new route is not classified. For each route it checks anonymous, another student, staff without the permission, staff with it, and the student. Business checks after the gate (`step_up_required`, `phone_required`) count as passing the gate.
- **Admin writes audited:** `tests/modules/ops/test_admin_writes_audited.py` performs every B1 admin write through the API and asserts exactly one audit row each, with the staff actor: role grant and revoke, runtime-config update, term create and delete, mute and lift, report resolve.
- **Volume tests:** job claim is now 1,000 jobs over 8 workers (was 200 over 4). A new test kills a worker after it claims a batch; its jobs run once after the lease expires. `tests/concurrency/test_relay_volume.py` relays 10,000 events through a sink that crashes once after its S3 write and before commit. The replay overwrites the same deterministic key, and S3 then holds exactly the 10,000 published ids.
- **No plain-text PII:** `tests/security/test_no_plaintext_pii.py` drives sign-up, guardian consent, step-up, phone change and Google sign-up and sign-in. It then scans every text, JSON, array and bytea column in the app schemas, and every Redis value, for the phones and email used. A planted control value proves the scan finds what it should.
- **Event contract:** `tests/contract/test_event_envelope.py` validates a real `user.signed_in` outbox row as `EventEnvelope` v1 and `UserSignedIn`. It also compares both JSON schemas with golden files in `tests/contract/golden/`, so a consumer-visible change must be deliberate (`UPDATE_GOLDEN=1`).
- **Deployables:** `scripts/smoke_deployables.sh` builds the image and starts all five deployables against the local services: `/readyz` 200 for api, ai-gateway and exam-ingest; `--check` exits 0 for workers and exam-consumers. It passed locally. It is not in CI yet because the CI image job has no services.
- **Load script:** `tests/load/auth.js` (k6) targets OTP verify and refresh at 100 + 100 req/s with p95 < 150 ms, with the SMS send excluded. It has not been run, and no capacity figure is claimed. Its preconditions are an open question: verify needs a known code, B1 accepts a fixed code only in local and test, and the auth rate limits must be raised for the run.

### Test plan file names
These §F test-plan entries are covered under other file names. The cases listed in the plan are all present.

| Spec file | Covered in |
|---|---|
| `tests/core/test_body_limits.py` | `tests/core/test_http_app.py`, `tests/core/test_http_hardening.py` |
| `tests/core/test_errors.py`, `tests/core/test_health.py` | `tests/core/test_http_app.py`, `tests/entrypoints/test_http_apps.py` |
| `tests/modules/auth/providers/test_google.py`, `test_facebook.py` | `tests/modules/auth/test_providers.py`, `test_providers_edge.py` |
| `tests/modules/auth/test_pending_signup.py` | `tests/modules/auth/test_services.py`, `test_end_to_end.py` |
| `tests/modules/auth/test_sessions.py` | `tests/modules/auth/test_me.py`, `test_tokens.py` |
| `tests/modules/auth/test_social_sign_in.py`, `test_social_link.py` | `tests/modules/auth/test_social.py`, `test_identities.py` |
| `tests/modules/nfr/test_consumer_dedupe.py`, `test_outbox_relay.py` | `tests/modules/nfr/test_relay.py` |
| `tests/modules/nfr/test_jobs_repo.py` | `tests/modules/nfr/test_jobs.py` |
| `tests/shared/test_dhaka_date.py` | `tests/shared/test_shared_helpers.py` |
| `tests/test_structure.py` | `tests/tooling/test_check_scripts.py` (the gate scripts themselves) |

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
- Revoke the account's other sessions after a phone change (SIM-swap hardening). Not done in B1.

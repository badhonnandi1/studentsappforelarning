# 18 · Security architecture

**Date:** 2026-11-27 · Scope: the backend deployables, edge Worker, data stores and third-party integrations. API conventions: [`14`](14_api_contracts.md) §1. Data rules: [`01`](01_database_design.md) §1, §5.5–§5.6. Operations: [`19`](19_devops_and_deployment.md).

Most users are minors in Bangladesh. The Personal Data Protection Act 2026 treats under-18s as children who need guardian consent (s.9) and face photos as sensitive data; the D4 legal review is still open, so every retention and consent value below is **[Assumption, pending D4]**.

---

## 1. Authentication

### 1.1 Learner sign-in methods

| Method | Build | Verification | Notes |
|---|---|---|---|
| Phone OTP (+88) | 1 | 6-digit code, HMAC-hashed (`code_hash`), 5-minute expiry, 5 attempts, single use | Limits in §5. Code compared in constant time. SMS template has no link. |
| Google | 1 | ID token: signature against Google JWKS (cached by `Cache-Control`, refetched on unknown `kid`), `iss ∈ {accounts.google.com, https://accounts.google.com}`, `aud ∈ GOOGLE_CLIENT_IDS` (web, Android, iOS), `exp`, `iat` skew ≤ 5 min, `nonce` equals the server-issued nonce | Provider access tokens never stored |
| Facebook | 1 | Graph API `GET /debug_token?input_token=…&access_token={app-id}|{app-secret}`: `is_valid`, `app_id == FACEBOOK_APP_ID`, `user_id`, `expires_at > now`; then `GET /me?fields=id,name,email` with `appsecret_proof` (HMAC-SHA256 of the token with the app secret). iOS Limited Login tokens are OIDC JWTs verified like Google's against Meta's JWKS, with the nonce. | Email from Facebook is treated as **unverified** |
| Apple | 8 | Identity token against Apple JWKS, `aud` = service id / bundle id, `nonce` (SHA-256 of the issued nonce), `exp` | Token revoked via Apple's REST endpoint on account deletion; server notifications endpoint handles consent revocation |
| Email and password | 8 | argon2id (`time_cost=3, memory_cost=64 MiB, parallelism=2`, re-hash on parameter change), breached-password check against the Have I Been Pwned Pwned Passwords range API (free and keyless; send only the first 5 SHA-1 hex characters and the `Add-Padding: true` header; 1 s timeout; on timeout the check is skipped and logged **[Decision]**; HIBP publishes no hard rate limit for this endpoint, so re-check its terms before launch), 10 failed attempts → 15-minute lock | Email verification required before sign-in |

**Nonce flow.** `POST /v1/auth/social/nonce` returns 32 random bytes (base64url), stored at `nonce:social:{nonce}` with a 5-minute TTL. Social verification deletes the key with `GETDEL`; a second use fails. This blocks replay of a captured provider token.

**Account-linking rules** (the main account-takeover risk for social sign-in):

1. An existing `(provider, provider_subject)` signs in to its linked user.
2. Otherwise, a **Google** identity with `email_verified = true` whose email hash matches a user with `email_verified_at IS NOT NULL` is linked automatically; the user receives an inbox and push notice "Google sign-in added".
3. **Facebook never links by email**, verified or not. Neither does Apple's private-relay email.
4. Otherwise a new account is needed. **No `users` row is created until a date of birth is supplied (R-24):** the response is `needs_profile` with a single-use pending sign-up token (15 min). `POST /v1/auth/sign-up/complete` runs the age gate before creation (under 13 via Facebook → `403 age_restricted`, nothing created), then age and consent (§6).
5. Linking more methods happens only from a signed-in session (`POST /v1/me/identities/{provider}`), and a session older than 15 minutes must re-verify a factor (OTP or the provider) first.
6. Unlinking requires a step-up OTP **and a verified phone on the account** (`403 phone_required`), and is refused (`409`) if no sign-in method would remain.
7. An identity already linked to another user returns `409 identity_in_use` without revealing that user.
8. Suspended or deleted users cannot sign in by any method; the error is the same as invalid credentials.

**Phone-number recycling, SIM swap and dormant accounts (R-25).** Phone OTP is the primary factor and the main recovery path, and Bangladeshi operators recycle numbers. So:
- **Step-up OTP:** a fresh OTP (`purpose=step_up`, a 10-minute `X-Step-Up-Token`) is required to unlink a sign-in method, change the phone, request deletion or change the guardian.
- **Dormant accounts:** no sign-in for 180 days plus a new `device_id` means OTP **and** a second factor where one exists (a linked Google or Facebook identity). Otherwise the account runs in restricted mode for 72 h: no phone change, no unlink, no payments, no export.
- **Phone change or recovery on a new device:** requires a second linked method or a support check with identity questions.
- **Guardian phone change:** re-runs consent with OTPs to the old and the new guardian numbers, or a support check.
- **Security notices:** every phone change, new-device sign-in after dormancy, and link or unlink sends an inbox and push notice to all sessions.

**Provider outage.** Verification calls have a 3-second timeout and a circuit breaker per provider; if Google or Facebook is down, the client is told to use phone OTP. Sign-in never depends on more than one external provider at a time.

**Meta obligations (B1).** `POST /v1/webhooks/facebook/data-deletion` verifies the `signed_request` (base64url payload, HMAC-SHA256 with the app secret, `algorithm == HMAC-SHA256`), unlinks the identity, enqueues deletion of Facebook-derived fields, and returns `{url, confirmation_code}` pointing to the status endpoint. The deauthorise callback unlinks. Both are audited.

### 1.2 Tokens and sessions

| Item | Design |
|---|---|
| Access token | JWT, EdDSA (Ed25519), 15 minutes, claims `sub`, `sid`, `roles`, `aud`, `iat`, `exp`, `jti`. Header `kid`. |
| Signing keys | Stored in AWS Secrets Manager; the active key and the previous key are both published in an internal JWKS (`core.security.jwks`) loaded at startup and refreshed every 5 minutes. Rotation every 90 days: add the new key as "next", promote after 24 h, retire the old key after 30 minutes past the last token it could have signed. Exam session tokens use a separate key pair so ingest holds only the exam public key. |
| Refresh token | 256-bit random, stored as SHA-256 hash, 30 days (12 h for staff), bound to `device_sessions.id`. Rotation on every use; presenting an already-rotated token revokes the whole `family_id` and the session, and writes a security audit event (race R15, [`01`](01_database_design.md) §5.2). |
| Session revocation | Revoking a session sets `revoked_at` and writes `revoked_sess:{sid}` in Redis for 15 minutes so access tokens die immediately; `api` checks the key per request (one Redis `EXISTS`). |
| Exam session token | Audience `exam-ingest`, `attempt_id`, `sid`, `epoch`, expiry `ends_at + EXAM_MAX_EXTENSION_MIN + grace`, so extensions never break live tokens. Ingest verifies the signature, expiry and `epoch` (latest epoch cached in the exam Redis on takeover), and enforces the real deadline from the exam status and the per-attempt `ends_at`. Re-issued through `POST /v1/exams/{id}/attempts/current/token` after a takeover or extension. |
| Staff access | **Built in Build 1 (R-07).**<br>• Staff sign in through SSO with a generic OIDC client (Google Workspace by default): authorisation code with PKCE, state and nonce.<br>• `aud=admin` tokens are issued only by `/v1/admin/auth/sso/callback`, and only when the ID token's `amr` shows MFA, the email domain is allowed, and a staff role grant already exists on the same `users` row.<br>• Admin tokens carry `sso=true` and `amr`; admin routes reject `aud=api` tokens and any token without `sso=true`.<br>• Staff refresh is 12 h; there is no local admin login in staging or prod.<br>• Staff sessions are IP-allow-listed in production **[Decision]**. |
| Cookies | Not used for the API (bearer tokens only), so CSRF does not apply to `/v1/*`. The admin web app also uses bearer tokens held in memory, with a refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie scoped to `/v1/auth/refresh`; that endpoint additionally checks an `Origin` allow-list. |

## 2. Authorization

- **Roles:** the eight AUTH-03 roles mapped to permission codes (`identity.role_permissions`), granted with scope (`global`, `track`, `subject`, `tenant`, `batch`) in `identity.role_grants`. Mentor, guardian and affiliate are scoped capabilities added in B7–B8.
- **`can(actor, permission, resource)`** in services: resolves the actor's grants (cached per request) and checks the scope against the resource's track, subject node, tenant or batch.
- **Object-level checks (BOLA):** every repository function that loads a user-owned resource by id takes the actor's `user_id` (or tenant) as a filter, so a wrong owner yields `404`, not `403`, and never leaks existence. Mandatory API tests for every id-bearing route: another user's id → 404; another tenant's id → 404.
- **Function-level checks:** admin routers are mounted under `/v1/admin` with a dependency that requires `aud=admin` plus the endpoint's permission; there is no admin route without a declared permission (a test walks the router table).
- **Teacher access (v2 §4.10):** a teacher reads only submissions of batches where they hold the `batch` grant; leaving or removal ends access to new work; operations access to submissions is audited.
- **Tenant isolation (B8):** Postgres RLS on tenant-carrying tables: `USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true)::uuid)`, set with `SET LOCAL` in each transaction by the repository layer; search, embeddings, caches and tutor retrieval apply the same filter. A break-glass role for platform staff is audited. Cross-tenant read tests run on every release.

## 3. OWASP API Security Top 10 (2023)

| Risk | Controls | Tests |
|---|---|---|
| API1 Broken object level authorization | Owner/tenant filters in repositories; 404 on mismatch; ids are UUIDv7 (not guessable sequences, but never relied on) | Cross-user and cross-tenant id tests on every id route (§2) |
| API2 Broken authentication | §1; OTP and auth rate limits; refresh reuse detection; nonce for social; constant-time comparisons | Token tamper, expired, wrong `aud`/`kid`, replayed nonce, reused refresh, OTP brute force |
| API3 Broken object property level authorization | Response schemas are explicit pydantic models (`extra="forbid"`); no ORM serialisation; answer keys excluded by schema in Test and exam modes; leaderboard schema has first name and institution only | Schema snapshot tests; "no `answer_key` in Test mode" test; leaderboard field allow-list test |
| API4 Unrestricted resource consumption | Rate-limit tiers ([`14`](14_api_contracts.md) §1.7); pagination max 100; request body limit 256 KB for JSON by default and 1 MB for the batch endpoints (`/v1/practice/answers:sync`, `/v1/events:batch`, exam ingest), with files only through presigned uploads; upload size limits; AI quotas, per-user cost ceiling, global budget breaker; statement timeouts | 429 tests per tier; oversized body; quota exhaustion |
| API5 Broken function level authorization | `aud=admin` + permission dependency on every admin route; router-table test | Student token on every admin route → 403 |
| API6 Unrestricted access to sensitive business flows | OTP limits and CAPTCHA/device-integrity challenge; coupon redemption once per user; trial once per product; referral credit idempotency; registration cap; content crawl limits | Abuse scenario tests (OTP storm, coupon replay, trial reuse) |
| API7 Server-side request forgery | No user-supplied URLs fetched by the server, except `video_url` (stored, never fetched) and import files (from our own presigned uploads only); provider base URLs from settings only; egress allow-list at the VPC (NAT + proxy) for worker containers | Import with an external URL is rejected |
| API8 Security misconfiguration | Settings validator refuses unsafe prod config (debug, wildcard CORS, missing secrets, memory queue, enabled provider without secrets); docs disabled in prod; security headers at the edge; containers non-root, read-only filesystem | Settings validator tests; header test on staging |
| API9 Improper inventory management | OpenAPI snapshot in CI; every endpoint in [`14`](14_api_contracts.md); versioned paths; staging and prod only behind Cloudflare | Snapshot diff gate |
| API10 Unsafe consumption of APIs | Provider responses validated with pydantic; timeouts, breakers; webhook signatures (§9); payment status confirmed by server-side query, never trusted from redirects or webhooks alone (v2 §7.2) | Malformed provider payload tests; forged webhook tests |

## 4. Input validation

- Pydantic v2 schemas with `extra="forbid"`, constrained strings (length, pattern), `AwareDatetime`, enums as `Literal`.
- Bangla text normalised to NFC and stripped of control characters (`shared.bangla_text.normalise`) before storage and moderation.
- Question content (authored HTML/LaTeX) is sanitised with an allow-list (`nh3`) at save time and rendered server-side with KaTeX in strict mode (`trust: false`, no `\href`, no `\url`).
- User-generated text (display names, error reports, posts, tickets) goes through `com.moderate()` and is output-encoded by clients; the API never returns user text as HTML.
- SQL only through SQLAlchemy parameters; no string-built SQL. Ruff `S608` is an error.

## 5. Rate limiting and OTP abuse

- Tiers and limits in [`14`](14_api_contracts.md) §1.7, enforced by one Lua sliding-window script in Redis keyed by user, device and IP; Cloudflare rate limits per IP in front.
- **OTP:** 3 per phone per 15 min, 5 per day, 10 per IP per hour, device limits; after a limit trips, a CAPTCHA (Cloudflare Turnstile) or Play Integrity check is required. The default Play Integrity quota is 10,000 requests per day per app (checked 2026-11-27). That is enough because the check runs only after a limit trips. A higher quota takes a request form and up to a week, and the app must be on Google Play with its Cloud project linked in Play Console. From 2027-02-16, unlinked projects stay capped at 10,000 per day whatever the custom quota. Linking the project is a B1 setup task. SMS cost alarm: spend per number prefix per hour over threshold pages on-call (international and premium prefixes blocked; only +880 mobile prefixes allowed).
- **Lobby protection:** a "sign in now" push at T−24 h before exams (v2 §6.2) reduces OTP demand.

## 6. Privacy for minors (NFR-07)

| Control | Design |
|---|---|
| Age | Date of birth is **required before an account exists**, for every method (pending sign-up token, §1.1; R-24). Age is computed server-side on the Dhaka date. Facebook sign-up or linking under 13 is refused (`403 age_restricted`) with a pointer to phone OTP, because Meta's minimum age is 13. |
| Guardian consent | Under-18s confirm a guardian phone by OTP (`identity.guardian_consents`, versioned text in `consent_documents`) before features that need it (batch join, handwriting upload, payments). Method may change after D4. |
| Defaults | Profile private by default; no public profiles; tutor never asks for contact details or photos of people. |
| Leaderboards | First name and institution only; opt-out by student or guardian (`privacy_settings`); no photo, phone or full name in any board API; institution labelled self-reported (C15). |
| Notifications | Non-critical push held 22:00–07:00 Dhaka for minors. |
| Sensitive data | Face photos are sensitive: profile photos optional, moderated; photo-solve images with people are rejected and deleted; proctoring (B9) only with specific consent. |
| Handwriting | Collected only in batches with consent; evaluation-set use needs separate consent; never used to train commercial models on non-commercial datasets (product strategy §5). |
| Retention and deletion | [`01`](01_database_design.md) §5.6. Export and deletion run as events (`user.deletion_requested` → each module anonymises its own data → `user.deletion_completed`), tracked in `data_requests.module_status`. Support approves at P0 (B6) within 30 days; automated in B9 (AUTH-10). Requests need a step-up OTP. |
| Transfer abroad | Hosting in AWS Mumbai; legal review D4 decides conditions. AI provider data handling documented; no training on our data by the provider (contract check **[Needs evidence]**). |

## 7. Secrets and encryption

| Item | Design |
|---|---|
| Secret store | AWS Secrets Manager (prod, staging); injected into ECS tasks as secrets, never baked into images; local dev uses `.env` with fake values only. `gitleaks` in pre-commit and CI. |
| In transit | TLS 1.2+ everywhere: Cloudflare ↔ client, Cloudflare ↔ ALB (Full strict with origin certificates), RDS and ElastiCache TLS required, SQS and S3 HTTPS endpoints via VPC endpoints. |
| At rest | RDS, ElastiCache, S3, SQS encrypted with KMS keys; R2 encrypted by default. |
| PII columns | Envelope encryption: a data key per environment (AES-256-GCM) wrapped by a KMS key; ciphertext stores key version + nonce + tag. Keyed lookup hashes (HMAC-SHA256 with a separate secret) for phone and email. Rotation: new data key version yearly; a background job re-encrypts rows lazily on read-write and in batches; hash key rotation requires a dual-hash migration window (both hashes looked up). |
| Exam papers | AES-256-GCM per exam key, released only by the edge Worker at start (v2 §6.2). |
| Logs | structlog processors redact keys named `phone`, `email`, `token`, `password`, `otp`, `answer_key`, `authorization`; a test asserts redaction. |

## 8. Secure file handling

- Uploads only through presigned S3 POST policies with `content-length-range`, exact `Content-Type`, and a key under `uploads/{purpose}/{user_id}/{uuid}`; URLs expire in 10 minutes.
- Purposes and limits: profile photo ≤ 2 MB JPEG/PNG; photo solve ≤ 1 MB JPEG (client downscales to 1,280 px); submission pages ≤ 3 MB JPEG; import files ≤ 50 MB (xlsx, csv, docx, json, pdf).
- After upload, a worker validates magic bytes, re-encodes images (Pillow, strips EXIF including GPS), rejects polyglots, and runs a malware scan on documents (**[Needs evidence]**: ClamAV in the worker image vs. a managed scanner) before the file is usable.
- Buckets are private; reads through short-lived signed URLs (5 minutes for media, 15 for PDFs); Cloudflare R2 signed URLs via the edge Worker for papers and media.
- Document parsing (docx, xlsx) runs in the worker with size and entity limits (defusedxml), no macros, in a separate queue with CPU and memory limits.

## 9. Webhooks and external integrations

| Source | Verification |
|---|---|
| bKash IPN via SNS | SNS message signature (certificate URL host must be `sns.<region>.amazonaws.com`), subscription confirmation handled once; then server-side status query before any capture (v2 §7.2) |
| SSLCommerz / aamarPay | Provider hash or validation API, then status query |
| Google Play RTDN | Pub/Sub push JWT (audience and service account), then Play Developer API purchase lookup |
| Apple App Store notifications v2 | JWS signed by Apple's certificate chain |
| Meta callbacks | `signed_request` HMAC (§1.1) |
| Apple sign-in notifications | JWS from Apple |

Every webhook is stored first in `commerce.provider_events` or `identity.apple_notifications` under a unique provider event id, then processed by a job; duplicates return 200 with no work.

## 10. Dependency and supply-chain security

- `uv.lock` pins hashes; Dependabot weekly; `pip-audit` in CI fails on high or critical; Trivy scans images (OS and Python layers) and fails on high or critical with a documented allow-list for unfixable base-image issues.
- Base images: `python:3.13-slim` pinned by digest; Node for KaTeX only in the worker image; images signed (cosign) and only signed images deploy.
- GitHub Actions pinned by commit SHA; OIDC to AWS (no long-lived keys).

## 11. Content protection and AI safety

- **NFR-06a:** question payloads only through authenticated APIs; media and papers through signed URLs; per-account distinct-question limit per hour (HyperLogLog `crawl:{user}:{hour}`); sequential-crawl detection (monotonic id or node walking) flags and slows the account; canary questions unique per account cohort to trace leaks (B6).
- **Offline packs (OFF-03, B7): accepted risk (R-30).** Learn mode needs answer keys on the device, so a rooted phone can extract a pack's chapter. Controls:
  - each pack is watermarked per user (per-user item ordering and an embedded user fingerprint);
  - each pack contains canary items unique to the user, to trace leaks;
  - at most 5 packs per user per day;
  - packs expire and are revoked with the entitlement;
  - packs never contain exam papers.

  The residual risk is accepted and recorded in [`20`](20_risk_register.md).
- **Streamed tutor output (R-10):** no unmoderated model text reaches a student.
  - For learners under 18 and for every free-form, non-canonical answer, the gateway buffers the whole answer until verification and output moderation pass, and sends only `stage` progress events meanwhile.
  - Adult cheap-tier answers are released sentence by sentence, each after incremental output moderation.
  - Only verified canonical cache hits stream immediately.
- **Vector search filters (R-23):** HNSW applies filters after the index scan, so a selective filter can silently drop permitted results.
  - pgvector ≥ 0.8 is required, with `hnsw.iterative_scan = relaxed_order` and a tuned `ef_search`.
  - Tenant-private content uses partial HNSW indexes (large tenants) or exact search (small tenants), always under RLS (B8).
  - Results are re-checked against permission filters after fusion.
  - The search gate includes chapter- and tenant-filtered queries.
- **AI safety (AI-05):** input and output moderation; scope classifier; fixed reviewed safe response for self-harm or abuse disclosures; tutor locked during live exams by the server, fail-closed; Anthropic minors' requirements (v2 §4.6) tracked as a launch checklist.
- **Prompt injection:** retrieved text and student writing are passed as documents/data, never concatenated into system instructions; instruction-like text in submissions is flagged (v2 §4.10); citations must resolve to the permission-filtered retrieved set; the model has no tools that write data; safety eval includes injection inside retrieved text (v2 §4.8).
- **Cache privacy:** canonical cache keys contain only content ids; entries generated without personal context; release test from v2 §4.8.

## 12. Audit logging

- Admin writes and security events per [`01`](01_database_design.md) §5.5.
- Security events logged: sign-in success and failure (method, coarse reason), OTP lockout, refresh reuse, session revoke, identity link and unlink, consent grant and withdrawal, role grant changes, data requests, break-glass use.
- Audit log is append-only (`REVOKE UPDATE, DELETE`), partitioned monthly, retained 3 years, and exported daily to S3 with Object Lock.

## 13. Penetration test and security checklist per build

External penetration test before payments go live (v2 week 20) and before launch; no open high or critical findings is a release gate (v2 §8.2).

| Build | Security items that must pass |
|---|---|
| 1 | Token tamper, `kid`, `aud`; refresh reuse; OTP limits; social nonce replay; linking matrix; Meta signed_request; PII encryption and log redaction; audit append-only; settings validator; admin route permission test |
| 2 | Content sanitisation; KaTeX strict; presigned upload limits; import file validation; author ≠ verifier; staff scope checks |
| 3 | BOLA on sessions, answers, bookmarks, notes; no key in Test mode; leaderboard privacy fields; replayed answer id from another user never returns their data; telemetry size limits |
| 4 | Exam lock fail-closed; quota bypass attempts; prompt-injection eval; cache privacy test; photo moderation and deletion; tutor never cites inaccessible content |
| 5 | Exam token audience and epoch; key not released before start; ingest has no DB access; late-answer rules; result not visible before publish |
| 6 | Payment verify-then-capture; forged webhooks; coupon and trial abuse; teacher cross-batch read; refund permission; crawl detection; pen test |
| 7 | Thread and mentor content moderation; mentor access scope; AI items isolated from the bank |
| 8 | RLS cross-tenant tests; parent link scope; Apple token checks; password policy; iOS IAP verification; campaign opt-out |
| 9 | Group chat minor-safety rules; proctor consent; marketplace payout data encryption; automated deletion completeness |

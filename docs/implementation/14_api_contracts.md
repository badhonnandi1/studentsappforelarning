# 14 · API contracts

**Date:** 2026-11-27 · This document holds the global API conventions and the **canonical endpoint index** for all nine builds. Per-endpoint request and response schemas, validation rules and error lists are in each build document, section D (`05_build_01.md` … `13_build_09.md`). A build document may not introduce an endpoint that is missing here; add it here first.

---

## 1. Conventions

### 1.1 Base paths and deployables

| Prefix | Deployable | Notes |
|---|---|---|
| `/v1/…` | `api` | All synchronous learner, content and admin APIs |
| `/v1/tutor/…`, `/v1/photo-solves/…` | `ai-gateway` | Routed at the edge by path; long-lived SSE |
| `/v1/ingest/…` | `exam-ingest` | Exam answer batches; no Postgres access |
| `/edge/…` | Cloudflare Worker | `/edge/time`, `/edge/exams/{id}/key` (B5) |
| `/v1/admin/…` | `api` | Staff only; SSO + 2FA session; every write audited |
| `/v1/webhooks/…` | `api` | Provider callbacks; signature-verified; no user auth |
| `/livez`, `/readyz` | every HTTP deployable | `/readyz` lists failing dependencies with 503 |

Versioning: the path carries the major version. Additive changes (new optional fields, new endpoints) need no version bump. A breaking change ships as a new path while the old one stays for one minimum-app-version cycle. The OpenAPI document is generated from FastAPI and snapshotted in `backend/openapi.json` (generated file, exempt from the 200-line rule); CI fails on an unreviewed diff.

### 1.2 Authentication and authorization

| Caller | Mechanism |
|---|---|
| Learner, parent, teacher | `Authorization: Bearer <access JWT>`: EdDSA (Ed25519), 15 min, claims `sub`, `sid` (device session), `roles`, `iat`, `exp`, `aud=api`. Refresh via `POST /v1/auth/refresh` with a rotating refresh token. |
| Staff (content, ops, super admin) | Same JWT with `aud=admin`, issued **only** by `GET /v1/admin/auth/sso/callback` after an OIDC sign-in whose `amr` shows MFA (B1, R-07). Claims add `sso=true` and `amr`. Valid 15 min; staff refresh tokens last 12 h. Admin routes reject any token without `sso=true`. There is no local admin login in staging or prod. |
| Exam ingest | Separate exam session JWT: `aud=exam-ingest`, `attempt_id`, `sid`, `epoch`, `exp = ends_at + EXAM_MAX_EXTENSION_MIN (default 60) + grace`, so an extension never expires tokens mid-exam. Ingest enforces the real deadline from the exam status (with extensions) and the attempt's `ends_at`. Verified with the public key only; re-issued by `POST /v1/exams/{id}/attempts/current/token`. |
| Workers, gateways | IAM role credentials; never user tokens. |
| Webhooks | Provider signature (bKash SNS signature, aggregator hash, Google Pub/Sub JWT, Meta `signed_request` HMAC, Apple JWS). |

Labels such as `Role:mentor` (the Teacher role plus permission `mentor.reply`), `Role:guardian (link)`, `Role:teacher (batch)`, `Role:batch.member` and `Role:room.member` are **relationship checks** performed by the owning module (an active guardian link, batch membership, room membership, or an approved teacher or mentor grant). They are not extra roles: the eight AUTH-03 roles stay fixed, and the relationship is verified on every request.

Authorization is `can(actor, action, resource)` in the owning module's service layer, never in routers. Every resource read by id checks ownership or a scoped grant (OWASP API1: broken object level authorization). The "Auth" column in §3 uses: **Public** (no token), **User** (any signed-in user), **Owner** (the resource's user), **Role:x** (permission from a scoped grant), **Staff:x** (admin audience + permission), **Signed** (webhook signature), **ExamToken**.

### 1.3 Request and response format

- JSON, UTF-8, `snake_case`. Timestamps ISO 8601 UTC with `Z`. Dhaka dates as `YYYY-MM-DD` with field names ending `_dhaka_date`.
- Money: `amount_poisha` (integer) plus `amount_display` (string, e.g. `"৳২৪৯.০০"` or `"৳249.00"` by `Accept-Language`).
- Ids: UUIDv7 strings.
- Bilingual content: the server returns the language requested by `lang` query or the profile default; both are returned only where the client needs both (editors).
- Lite mode (OFF-02): `X-Lite-Mode: 1` or `?lite=1` omits image bytes and inline media, returning `media_ref` placeholders; responses are always compressed (`br` or `gzip`).
- Minimum app version: every response carries `X-Min-App-Version`; requests from older apps receive `426 upgrade_required` on breaking paths.
- Body size: 256 KB maximum for JSON by default; 1 MB for the batch endpoints (`/v1/practice/answers:sync`, `/v1/events:batch`, `/v1/ingest/…`). Files never pass through the API: they go to presigned uploads. Oversized bodies get 413 `payload_too_large`.
- Sensitive actions (unlinking a sign-in method, changing the phone, requesting deletion, changing the guardian) require `X-Step-Up-Token` from `POST /v1/auth/step-up`, or they fail with 403 `step_up_required`.

### 1.4 Pagination, filtering and sorting

Cursor pagination only: `?limit=` (default 20, max 100) and `?cursor=` (opaque, base64url of the sort key). Response: `{"items": [...], "next_cursor": "…" | null}`. No offset pagination on user-facing lists. Admin lists may add `?sort=` from an allow-list per endpoint.

### 1.5 Errors

All errors use one envelope (starter `core.errors`):

```json
{"error": {"code": "attempt_open", "message": "…", "details": {…}, "request_id": "…"}}
```

| HTTP | `code` examples | When |
|---|---|---|
| 400 | `bad_request` | Malformed input outside schema validation |
| 401 | `unauthorized`, `token_expired` | Missing or invalid token |
| 403 | `forbidden`, `age_restricted`, `consent_required` | Authenticated but not allowed |
| 404 | `not_found` | Missing, or not visible to this caller (never leaks existence) |
| 409 | `conflict`, `attempt_open`, `identity_in_use`, `already_registered`, `version_conflict` | State conflict |
| 410 | `expired` | Expired codes, links, orders |
| 422 | `validation_error`, `idempotency_key_reused` | Schema or business validation |
| 423 | `locked_exam` | Tutor during a live exam |
| 426 | `upgrade_required` | App below minimum version |
| 429 | `too_many_requests`, `quota_exhausted` | Rate limit or quota; `Retry-After` header |
| 503 | `unavailable`, `kill_switch` | Dependency down or feature switched off |

Domain-specific codes used by the build documents (all use the envelope above):

| HTTP | Code | Build | Meaning |
|---|---|---|---|
| 403 | `consent_required` | 1, 6 | Under-18 action needs guardian consent first |
| 403 | `solutions_locked` | 5 | Review requested before `solution_unlock_at` |
| 409 | `stream_in_progress` | 4 | A second concurrent tutor stream for the same user |
| 409 | `batch_in_flight`, `seq_gap` | 5 | Exam ingest: one batch in flight; a non-contiguous batch |
| 409 | `exam_full` | 5 | Registration cap reached |
| 409 | `order_pending` | 6 | An unpaid order for the same product already exists |
| 401 | `session_taken_over` | 5 | Exam token epoch is stale after a device takeover |
| 410 | `entry_closed` | 5 | Late-entry window over |
| 422 | `rubric_missing`, `retake_required` | 6 | Written task question has no rubric; page fails quality checks |
| 422 | `coupon_invalid`, `refund_not_allowed` | 6 | Coupon rules; refund rules (e.g. live-exam fee after start) |
| 402 | `payment_unverified` | 6 | Capture not yet verified with the provider |
| 425 | `too_early` | 5 | Attempt start before the exam opens |
| 403 | `step_up_required`, `phone_required`, `mfa_required`, `age_restricted` | 1 | Missing step-up token; unlink without a verified phone; staff SSO without MFA; under-13 Facebook |
| 413 | `payload_too_large` | 1 | Body above the limit in §1.3 |
| 429 | `content_rate_limited` | 6 | Distinct-question or crawl limit (NFR-06a) |

Validation errors list fields: `details.fields = [{"loc": ["body","answer_id"], "msg": "…"}]`.

### 1.6 Idempotency

- All `POST` endpoints that create or charge accept `Idempotency-Key` (UUID). It is **required** where the column "Idem" says **R**, optional (**O**) elsewhere, and not applicable (–) for reads.
- Practice answers use the body `answer_id` as the key (unique per user). Exam batches use `(attempt_id, seq)`.
- Replays return the original status and body with header `Idempotent-Replay: true`. A different body with the same key returns `422 idempotency_key_reused`.

### 1.7 Rate-limit tiers

Enforced in Redis by user, device and IP (sliding window), plus edge limits by IP at Cloudflare. Values are **[Rule]** starting points, configured in `runtime_config`.

| Tier | Limit | Used for |
|---|---|---|
| **T-otp** | 3 per phone per 15 min, 5 per day; 10 per IP per hour; CAPTCHA or device-integrity challenge when tripped | OTP send |
| **T-auth** | 20 per IP per min; 10 per device per min | Sign-in, social, refresh |
| **T-write** | 120 per user per min | Ordinary writes |
| **T-answer** | 60 per user per min (burst 20) | Practice answers |
| **T-read** | 600 per user per min | Ordinary reads |
| **T-content** | Distinct question ids per user per hour ≤ 600 (NFR-06a), plus sequential-crawl detection | Question payload reads |
| **T-ai** | 10 per user per min, 1 concurrent stream per user; plus plan quotas | Tutor and photo solve |
| **T-upload** | 30 presigned URLs per user per hour | Uploads |
| **T-admin** | 300 per staff user per min | Admin |
| **T-webhook** | 1,000 per provider per min | Webhooks |
| **T-ingest** | 1 in-flight batch per attempt; 10 per attempt per min | Exam ingest |

---

## 2. Shared payload shapes

| Shape | Fields |
|---|---|
| `TokenPair` | `access_token`, `access_expires_at`, `refresh_token`, `refresh_expires_at`, `session_id`, `user` (`UserSummary`) |
| `UserSummary` | `id`, `display_name`, `first_name`, `is_minor`, `roles[]`, `needs_consent`, `needs_profile` |
| `QuestionPayload` | `question_version_id`, `question_id`, `type`, `lang`, `body_html`, `options[] {label, html}`, `media[] {kind, url|media_ref, alt}`, `marks`, `time_estimate_s`, `subparts[]` (CQ). Never contains `answer_key` in Test mode or exams. |
| `AnswerResult` | `answer_id`, `duplicate`, and in Learn mode `is_correct`, `answer_key`, `explanation_html`, `effective_at`, `xp_awarded`, `reward_pending` |
| `Page<T>` | `items[]`, `next_cursor` |
| `Money` | `amount_poisha`, `amount_display` |
| `EventEnvelope` | v2 §3.3 envelope |

---

## 3. Canonical endpoint index

Columns: **B** build · **Auth** (§1.2) · **RL** rate tier (§1.7) · **Idem** (§1.6).

### 3.1 Platform and health (NFR)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/livez` | Liveness, no dependencies | Public | – | – | 1 |
| GET | `/readyz` | Readiness with dependency checks | Public | – | – | 1 |
| GET | `/v1/config/client` | Kill switches, min app version, support links, feature flags (B8) | Public | T-read | – | 1 |
| POST | `/v1/events:batch` | Client telemetry into the event log | User | T-write | O | 3 |
| GET | `/v1/uploads/{purpose}/presign` | Presigned upload URL (profile photo, photo solve, submission page, import file) | User or Staff | T-upload | – | 1 |

### 3.2 Identity and access (AUTH)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| POST | `/v1/auth/otp/send` | Send sign-in OTP (+88) | Public | T-otp | O | 1 |
| POST | `/v1/auth/otp/verify` | Verify OTP; sign in or sign up; returns `TokenPair` | Public | T-auth | O | 1 |
| POST | `/v1/auth/social/nonce` | Single-use nonce for social sign-in (5 min) | Public | T-auth | – | 1 |
| POST | `/v1/auth/social/{provider}` | Sign in or sign up with Google or Facebook (Apple in 8) | Public | T-auth | O | 1 |
| POST | `/v1/auth/refresh` | Rotate refresh token | Public (refresh token) | T-auth | – | 1 |
| POST | `/v1/auth/sign-up/complete` | Create the account once DOB is supplied (pending sign-up token from OTP or social, R-24) | Public (pending token) | T-auth | – | 1 |
| POST | `/v1/auth/step-up` | Exchange a fresh OTP for a 10-minute step-up token (unlink, phone change, deletion, guardian change) | User | T-otp | – | 1 |
| GET | `/v1/admin/auth/sso/start` | Staff OIDC sign-in start (PKCE, state, nonce) | Public | T-auth | – | 1 |
| GET | `/v1/admin/auth/sso/callback` | Staff OIDC callback; issues `aud=admin` tokens only when MFA is present | Public | T-auth | – | 1 |
| POST | `/v1/auth/logout` | Revoke current session | User | T-write | – | 1 |
| GET | `/v1/me` | Current user, roles, flags | User | T-read | – | 1 |
| PATCH | `/v1/me` | Display name, first name, locale (moderated) | User | T-write | – | 1 |
| GET | `/v1/me/sessions` | Device sessions | User | T-read | – | 1 |
| DELETE | `/v1/me/sessions/{session_id}` | Revoke a session | Owner | T-write | – | 1 |
| GET | `/v1/me/identities` | Linked sign-in methods | User | T-read | – | 1 |
| POST | `/v1/me/identities/{provider}` | Link Google or Facebook (Apple 8) to the signed-in account | User | T-auth | O | 1 |
| DELETE | `/v1/me/identities/{provider}` | Unlink (refused if last method) | User | T-write | – | 1 |
| POST | `/v1/me/phone` | Add or change phone (OTP purpose `phone_change`) | User | T-otp | O | 1 |
| GET | `/v1/me/profile` | Student profile | User | T-read | – | 1 |
| PUT | `/v1/me/profile` | Update profile (class, group, version, curriculum, institution, district, upazila, board, exam year) | User | T-write | – | 1 |
| POST | `/v1/me/profile/photo` | Confirm uploaded profile photo (moderated) | User | T-write | O | 1 |
| GET | `/v1/me/privacy` | Privacy settings | User | T-read | – | 1 |
| PUT | `/v1/me/privacy` | Leaderboard opt-out, privacy | User | T-write | – | 1 |
| POST | `/v1/me/consent/guardian/start` | Send OTP to guardian phone (under-18) | User | T-otp | O | 1 |
| POST | `/v1/me/consent/guardian/confirm` | Confirm guardian OTP, record consent | User | T-auth | O | 1 |
| GET | `/v1/consent-documents/{version}` | Consent and privacy text | Public | T-read | – | 1 |
| GET | `/v1/reference/districts` | Districts and upazilas | Public | T-read | – | 1 |
| GET | `/v1/reference/institutions` | Search institution reference list (`?q=`, `?district_id=`) | Public | T-read | – | 1 |
| GET | `/v1/me/enrolments` | Track enrolments | User | T-read | – | 2 |
| POST | `/v1/me/enrolments` | Enrol in a track and exam year | User | T-write | O | 2 |
| PATCH | `/v1/me/enrolments/{id}` | Change group or version; close | Owner | T-write | – | 2 |
| POST | `/v1/me/enrolments/{id}:promote` | Track promotion with history (AUTH-06) | Owner | T-write | R | 7 |
| POST | `/v1/me/data-requests` | Request export or deletion | User | T-write | R | 6 |
| GET | `/v1/me/data-requests` | Status of requests | User | T-read | – | 6 |
| GET | `/v1/me/data-export/{id}` | Download export (signed URL) | Owner | T-read | – | 9 |
| GET | `/v1/me/consents` | Consent dashboard: consents held, versions, scopes | User or Role:guardian (link) | T-read | – | 9 |
| DELETE | `/v1/me/data-requests/{id}` | Cancel a deletion during its grace period | Owner | T-write | – | 9 |
| POST | `/v1/me/consents/{id}:withdraw` | Withdraw a consent (guardian or student per scope) | User or Role:guardian (link) | T-write | R | 9 |
| POST | `/v1/devices/{device_id}/profiles` | Add an account to a shared device (AUTH-08) | User | T-write | O | 8 |
| GET | `/v1/devices/{device_id}/profiles` | List accounts on a device | User | T-read | – | 8 |
| DELETE | `/v1/devices/{device_id}/profiles/{user_id}` | Remove an account from a device | User | T-write | – | 8 |
| POST | `/v1/auth/password/sign-up` | Email and password sign-up | Public | T-auth | O | 8 |
| POST | `/v1/auth/password/sign-in` | Email and password sign-in | Public | T-auth | – | 8 |
| POST | `/v1/auth/password/reset` | Request reset | Public | T-otp | – | 8 |
| POST | `/v1/auth/password/reset/confirm` | Confirm reset | Public | T-auth | – | 8 |
| POST | `/v1/auth/email/verify` | Verify email token | Public | T-auth | – | 8 |
| POST | `/v1/webhooks/facebook/data-deletion` | Meta data-deletion callback (signed_request) | Signed | T-webhook | – | 1 |
| GET | `/v1/auth/social/facebook/deletion-status/{code}` | Deletion status page data | Public | T-read | – | 1 |
| POST | `/v1/webhooks/facebook/deauthorize` | Meta deauthorise callback | Signed | T-webhook | – | 1 |
| POST | `/v1/webhooks/apple/notifications` | Apple server-to-server notifications | Signed | T-webhook | – | 8 |
| GET | `/v1/admin/users` | User lookup by phone hash, email hash or id | Staff:user.read | T-admin | – | 6 |
| GET | `/v1/admin/users/{id}` | User detail (sessions, enrolments, entitlements via PAY) | Staff:user.read | T-admin | – | 6 |
| POST | `/v1/admin/users/{id}:suspend` | Suspend or reinstate | Staff:user.write | T-admin | R | 6 |
| POST | `/v1/admin/role-grants` | Grant a scoped role | Staff:role.grant | T-admin | R | 1 |
| DELETE | `/v1/admin/role-grants/{id}` | Revoke a role grant | Staff:role.grant | T-admin | – | 1 |
| GET | `/v1/admin/data-requests` | Data request queue | Staff:privacy | T-admin | – | 6 |
| POST | `/v1/admin/data-requests/{id}:complete` | Execute export or deletion | Staff:privacy | T-admin | R | 6 |

### 3.3 Community and moderation (COM)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| POST | `/v1/reports` | Report content or a user | User | T-write | O | 1 |
| GET | `/v1/admin/moderation/reports` | Report queue | Staff:moderation | T-admin | – | 1 |
| POST | `/v1/admin/moderation/reports/{id}:resolve` | Resolve a report | Staff:moderation | T-admin | R | 1 |
| POST | `/v1/admin/moderation/restrictions` | Mute or ban | Staff:moderation | T-admin | R | 1 |
| DELETE | `/v1/admin/moderation/restrictions/{id}` | Lift | Staff:moderation | T-admin | – | 1 |
| GET/POST/DELETE | `/v1/admin/moderation/terms[/{id}]` | Manage term list | Staff:moderation | T-admin | O | 1 |
| GET | `/v1/questions/{question_id}/thread` | Discussion thread for a question | User | T-read | – | 7 |
| POST | `/v1/threads/{thread_id}/posts` | Post a reply (moderated) | User | T-write | O | 7 |
| POST | `/v1/posts/{post_id}/vote` | Upvote | User | T-write | – | 7 |
| POST | `/v1/posts/{post_id}:pin` | Pin a verified-teacher answer | Role:teacher.verified | T-write | – | 7 |
| POST | `/v1/mentor-requests` | Escalate a tutor question to a mentor (paid) | User | T-write | R | 7 |
| GET | `/v1/mentor-requests/{id}` | Request status and replies | Owner | T-read | – | 7 |
| GET | `/v1/mentor/queue` | Mentor queue with SLA | Role:mentor | T-read | – | 7 |
| POST | `/v1/mentor/requests/{id}/replies` | Reply by text, image or voice | Role:mentor | T-write | O | 7 |
| GET/POST | `/v1/forums/{category_id}/threads` | Subject forum | User | T-read / T-write | O | 9 |
| GET/POST | `/v1/study-groups` | List and create groups | User | T-read / T-write | O | 9 |
| POST | `/v1/study-groups/{id}/members` | Join or invite (minor-safety rules) | User | T-write | O | 9 |
| GET/POST | `/v1/study-groups/{id}/messages` | Group messages | Role:group.member | T-read / T-write | O | 9 |

### 3.4 Curriculum (TAX)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/tracks` | Tracks (edge-cached) | Public | T-read | – | 2 |
| GET | `/v1/tracks/{track_id}/syllabus-versions` | Syllabus versions by year | Public | T-read | – | 2 |
| GET | `/v1/syllabus-versions/{id}/tree` | Taxonomy tree (`?depth=`, `?root=`) | Public | T-read | – | 2 |
| GET | `/v1/nodes/{node_id}` | One node with children and path | Public | T-read | – | 2 |
| GET | `/v1/tracks/{track_id}/exam-dates` | Exam dates by year | Public | T-read | – | 2 |
| GET | `/v1/nodes/{node_id}/links` | Cross-track linked topics (TAX-06) | Public | T-read | – | 7 |
| POST/PATCH | `/v1/admin/tracks[/{id}]` | Manage tracks | Staff:curriculum | T-admin | R | 2 |
| POST/PATCH | `/v1/admin/syllabus-versions[/{id}]` | Manage syllabus versions (copy-forward from a previous year) | Staff:curriculum | T-admin | R | 2 |
| POST/PATCH | `/v1/admin/nodes[/{id}]` | Create, edit, move, reorder nodes | Staff:curriculum | T-admin | R | 2 |
| POST | `/v1/admin/nodes:import` | Bulk tree import (CSV/JSON) | Staff:curriculum | T-admin | R | 2 |
| POST/DELETE | `/v1/admin/topic-links[/{id}]` | Manage topic links | Staff:curriculum | T-admin | R | 7 |
| PUT | `/v1/admin/tracks/{id}/exam-dates/{year}` | Set exam date | Staff:curriculum | T-admin | – | 2 |

### 3.5 Question bank and CMS (QB, CMS)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| POST | `/v1/admin/questions` | Create a draft question with first version | Role:content.author | T-admin | R | 2 |
| GET | `/v1/admin/questions/{id}` | Question with versions and workflow state | Role:content.read | T-admin | – | 2 |
| PUT | `/v1/admin/questions/{id}/draft` | Autosave editor draft | Role:content.author | T-admin | – | 2 |
| POST | `/v1/admin/questions/{id}/versions` | Create a new version from the draft (edits never mutate published versions) | Role:content.author | T-admin | R | 2 |
| POST | `/v1/admin/questions/{id}:preview` | Render preview (KaTeX, Bangla, mobile) | Role:content.author | T-admin | – | 2 |
| POST | `/v1/admin/questions/{id}:submit-review` | Draft → In Review | Role:content.author | T-admin | R | 2 |
| POST | `/v1/admin/question-versions/{id}/verifications` | Blind key entry by a verifier | Role:content.verify | T-admin | R | 2 |
| POST | `/v1/admin/question-versions/{id}:publish` | Verified → Published | Role:content.publish | T-admin | R | 2 |
| POST | `/v1/admin/question-versions/{id}:retire` | Retire | Role:content.publish | T-admin | R | 2 |
| GET | `/v1/admin/questions` | Search and filter bank by any metadata (lexical in 2, hybrid in 4) | Role:content.read | T-admin | – | 2 |
| POST | `/v1/admin/questions:bulk` | Bulk edit, tag, move | Role:content.author | T-admin | R | 2 |
| GET | `/v1/admin/assignments` | My review and verification queue | Role:content.read | T-admin | – | 2 |
| POST | `/v1/admin/assignments` | Assign work | Role:content.lead | T-admin | R | 2 |
| POST/PATCH | `/v1/admin/papers[/{id}]` | Manage previous-year papers | Role:content.author | T-admin | R | 2 |
| POST/PATCH | `/v1/admin/concept-notes[/{id}]` | Manage concept notes (cheat and formula sheets in 7) | Role:content.author | T-admin | R | 2 |
| POST | `/v1/admin/imports` | Start a bulk import (Excel, CSV, Word, JSON; PDF and image in 4) | Role:content.author | T-admin | R | 2 |
| GET | `/v1/admin/imports/{id}` | Import status and validation report | Role:content.author | T-admin | – | 2 |
| POST | `/v1/admin/imports/{id}:commit` | Create drafts from valid rows | Role:content.author | T-admin | R | 2 |
| GET | `/v1/admin/imports/{id}/pages` | OCR page results | Role:content.author | T-admin | – | 4 |
| GET | `/v1/admin/duplicates` | Duplicate candidates queue | Role:content.read | T-admin | – | 4 |
| POST | `/v1/admin/duplicates/{id}:decide` | Merge, mark variant or keep | Role:content.lead | T-admin | R | 4 |
| GET | `/v1/admin/error-reports` | Error-report queue with SLA ages | Role:content.triage | T-admin | – | 2 |
| POST | `/v1/admin/error-reports/{id}:triage` | Triage, merge, reject | Role:content.triage | T-admin | R | 2 |
| POST | `/v1/admin/error-reports/{id}:resolve` | Resolve; opens a correction if the key changes | Role:content.triage | T-admin | R | 3 |
| GET | `/v1/admin/corrections/{id}` | Rescoring progress | Role:content.read | T-admin | – | 3 |
| POST | `/v1/admin/corrections/{id}:approve-merit` | Approve merit republication after rescoring | Staff:exam.publish | T-admin | R | 5 |
| GET | `/v1/admin/ai-review-items` | AI feedback review queue | Role:content.triage | T-admin | – | 4 |
| POST | `/v1/admin/ai-review-items/{id}:resolve` | Correct cache, add eval case, raise error report, change prompt | Role:content.triage | T-admin | R | 4 |
| POST | `/v1/admin/ai-drafts` | Request AI drafts (explanation, variant, translation, tags, wrong key) | Role:content.author | T-admin | R | 7 |
| POST | `/v1/admin/ai-drafts/{id}:decide` | Accept or reject | Role:content.author | T-admin | R | 7 |
| GET | `/v1/admin/reports/coverage` | Content coverage dashboard | Role:content.read | T-admin | – | 7 |
| GET | `/v1/admin/reports/authors` | Author productivity and payments | Staff:content.finance | T-admin | – | 7 |
| POST | `/v1/admin/author-payouts:run` | Create payouts for a period | Staff:content.finance | T-admin | R | 7 |
| POST/PATCH | `/v1/admin/question-families[/{id}]` | Manage variant families | Role:content.author | T-admin | R | 7 |
| POST/PATCH | `/v1/admin/flashcard-decks[/{id}]` | Editorial decks | Role:content.author | T-admin | R | 7 |
| POST/PATCH | `/v1/admin/current-affairs[/{id}]` | Daily current-affairs items | Role:content.author | T-admin | R | 7 |
| GET/POST | `/v1/admin/media` | Media library (CMS-10) | Role:content.author | T-admin | R | 9 |
| POST | `/v1/questions/{question_id}/error-reports` | Student "Report error" (PRAC-07) | User | T-write | O | 3 |
| GET | `/v1/papers` | Browse previous-year papers (`?board=&year=&unit=&track=`) | User | T-read | – | 3 |
| GET | `/v1/papers/{id}` | Paper detail (questions only through a session) | User | T-read | – | 3 |
| GET | `/v1/concept-notes/{id}` | Concept note | User | T-content | – | 3 |
| GET | `/v1/nodes/{node_id}/concept-notes` | Notes, cheat sheets and formula sheets for a topic | User | T-content | – | 7 |
| GET | `/v1/search/questions` | Learner search (Bangla, Banglish, maths, semantic), entitlement-filtered | User | T-content | – | 4 |
| GET | `/v1/flashcard-decks` | Decks for a node; user decks | User | T-read | – | 7 |
| POST | `/v1/flashcard-decks` | Create a user deck | User | T-write | O | 7 |
| POST/PATCH/DELETE | `/v1/flashcard-decks/{id}/cards[/{card_id}]` | Manage cards in a user deck | Owner | T-write | O | 7 |
| GET | `/v1/current-affairs` | Daily feed and monthly compilations | User | T-read | – | 7 |
| GET | `/v1/questions/{question_version_id}/stats` | Item statistics (staff) | Role:content.read | T-admin | – | 7 |

### 3.6 Practice (PRAC)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/home` | Path of topics, "tomorrow" card, review mistakes, countdown, banners | User | T-read | – | 3 |
| POST | `/v1/practice/sessions` | Start session: lesson, custom builder, chapter, textbook, past paper, mistakes, weak topic, similar (photo) | User | T-write | R (`client_session_id`) | 3 |
| GET | `/v1/practice/sessions/{id}` | Session with question payloads (resume) | Owner | T-content | – | 3 |
| POST | `/v1/practice/sessions/{id}/answers` | Save answer (Learn returns result; Test returns receipt) | Owner | T-answer | R (`answer_id`) | 3 |
| POST | `/v1/practice/answers:sync` | Batch sync of offline answers (up to 50) | User | T-answer | R (per `answer_id`) | 3 |
| POST | `/v1/practice/sessions/{id}:complete` | Complete and get summary (XP, streak, next) | Owner | T-write | R | 3 |
| POST | `/v1/practice/sessions/{id}:abandon` | Abandon | Owner | T-write | – | 3 |
| POST | `/v1/practice/answers/{answer_id}/self-mark` | Self-mark a written answer against the rubric (`scoring_source=self`) | Owner | T-write | R | 3 |
| GET | `/v1/practice/mistakes` | Mistake Notebook (`?subject=`) | User | T-read | – | 3 |
| GET | `/v1/practice/bookmark-folders` | Folders | User | T-read | – | 3 |
| POST/PATCH/DELETE | `/v1/practice/bookmark-folders[/{id}]` | Manage folders | User | T-write | O | 3 |
| PUT/DELETE | `/v1/practice/bookmarks/{question_id}` | Bookmark (with folder) or remove | User | T-write | – | 3 |
| GET | `/v1/practice/bookmarks` | List bookmarks | User | T-read | – | 3 |
| PUT/DELETE | `/v1/practice/notes/{question_id}` | Personal note | User | T-write | – | 3 |
| GET | `/v1/practice/reviews/due` | Due spaced-repetition reviews | User | T-read | – | 7 |
| POST | `/v1/practice/reviews/{card_id}/grade` | Grade a review (again, hard, good, easy) and reschedule | Owner | T-write | R | 7 |
| POST | `/v1/practice/answers/{answer_id}/ai-estimate` | AI "practice estimate" for a self-practice written answer (only subjects that pass the higher gate) | Owner | T-ai | R | 6 |
| POST | `/v1/practice/daily-mix` | Get or create today's Daily Mix | User | T-write | R | 7 |
| POST | `/v1/practice/diagnostic` | Start the onboarding diagnostic | User | T-write | R | 7 |
| GET | `/v1/practice/abilities` | Per-topic ability (adaptive) | User | T-read | – | 7 |
| POST | `/v1/practice/offline-packs` | Build or refresh an encrypted offline chapter pack (entitlement-bound) | User | T-write | R | 7 |
| GET | `/v1/practice/offline-packs` | My packs with expiry and status | User | T-read | – | 7 |
| POST | `/v1/duels` | Create a duel or group room | User | T-write | R | 9 |
| POST | `/v1/duels/{code}:join` | Join by code | User | T-write | – | 9 |
| GET | `/v1/duels/{id}` | Room state and results | Role:room.member | T-read | – | 9 |
| WS | `/v1/realtime/duels/{id}` | Realtime room channel (separate `realtime` deployable) | Role:room.member | T-write | – | 9 |

### 3.7 Analytics (ANL)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/progress/dashboard` | Readiness per track; accuracy by subject, chapter, topic; attempts, study time, streak | User | T-read | – | 3 |
| GET | `/v1/progress/weak-areas` | Top N weakest topics (≥ 10 attempts) | User | T-read | – | 3 |
| GET | `/v1/progress/exam-history` | Score and rank trends | User | T-read | – | 5 |
| GET | `/v1/progress/mastery` | Mastery map heatmap | User | T-read | – | 7 |
| GET | `/v1/progress/time-analytics` | Time vs accuracy, guesses, negative-mark loss | User | T-read | – | 7 |
| GET | `/v1/progress/trends` | Previous-year chapter frequency, most-asked, predicted important | User | T-read | – | 7 |
| GET | `/v1/progress/percentile` | Peer percentile | User | T-read | – | 7 |
| GET | `/v1/progress/forecast` | Readiness forecast to exam date | User | T-read | – | 7 |
| POST | `/v1/progress/reports` | Request a PDF progress report | User or Role:guardian or Role:teacher | T-write | R | 9 |
| GET | `/v1/progress/reports/{id}` | Report status and signed URL | Owner | T-read | – | 9 |

### 3.8 AI tutor (AI)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/tutor/threads` | Threads per subject per enrolment | User | T-read | – | 4 |
| POST | `/v1/tutor/threads` | New chat for a subject | User | T-write | O | 4 |
| GET | `/v1/tutor/threads/{id}/messages` | Thread history | Owner | T-read | – | 4 |
| DELETE | `/v1/tutor/threads/{id}` | Delete a thread | Owner | T-write | – | 4 |
| POST | `/v1/tutor/messages` | Ask (SSE stream: `delta`, `citation`, `final`); explain actions (AI-04) | User | T-ai | R | 4 |
| POST | `/v1/tutor/messages/{id}/feedback` | Thumbs up or down with reason | Owner | T-write | – | 4 |
| GET | `/v1/tutor/quota` | Today's usage and limits | User | T-read | – | 4 |
| POST | `/v1/photo-solves` | Register an uploaded photo; runs moderation and OCR | User | T-ai | R | 4 |
| GET | `/v1/photo-solves/{id}` | OCR result and confidence | Owner | T-read | – | 4 |
| POST | `/v1/photo-solves/{id}:confirm` | Confirm or edit the recognised problem; SSE solution | Owner | T-ai | R | 4 |
| POST | `/v1/photo-solves/{id}/practice` | Start a session from the 3 similar questions | Owner | T-write | R | 4 |
| PUT | `/v1/tutor/threads/{id}/mode` | Socratic or direct mode (respects locks) | Owner | T-write | – | 7 |
| POST | `/v1/ai/quizzes` | Generate an AI quiz from a topic, notes or photo | User | T-ai | R | 7 |
| GET | `/v1/ai/summaries/{chapter_node_id}` | Chapter summary sheets | User | T-content | – | 7 |
| POST | `/v1/ai/coach/plan` | Generate or re-plan the weekly study plan | User | T-ai | R | 7 |
| GET | `/v1/ai/misconceptions` | Misconception clusters and fix sets | User | T-read | – | 7 |
| POST | `/v1/ai/voice/transcribe` | Bangla speech to text | User | T-ai | R | 9 |
| POST | `/v1/ai/voice/speak` | Text to speech for an explanation | User | T-ai | O | 9 |
| POST | `/v1/ai/spoken-english/sessions` | Spoken English conversation session | User | T-ai | R | 9 |
| POST | `/v1/ai/viva/sessions` | Viva or interview simulator session | User | T-ai | R | 9 |
| POST | `/v1/ai/spoken-english/sessions/{id}/turns` | One spoken-English turn (audio in, feedback and reply out) | Owner | T-ai | R | 9 |
| POST | `/v1/ai/viva/sessions/{id}/turns` | One viva turn with scored feedback | Owner | T-ai | R | 9 |
| GET | `/v1/admin/ai/usage` | Cost per user, route and day | Staff:ai.read | T-admin | – | 4 |
| GET | `/v1/admin/ai/evals` | Eval runs and gate results | Staff:ai.read | T-admin | – | 4 |
| POST | `/v1/admin/ai/canonical-answers/{id}:correct` | Correct or retire a cached answer | Role:content.triage | T-admin | R | 4 |
| POST/PATCH | `/v1/admin/ai/sources[/{id}]` | Register textbook sources and licence status (D1) | Staff:ai.content | T-admin | R | 4 |
| POST | `/v1/admin/ai/summaries/{id}:review` | Review a chapter summary | Role:content.triage | T-admin | R | 7 |

### 3.9 Teacher-checked written marking (AI + INST)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| POST | `/v1/teacher/applications` | Apply for a teacher account | User | T-write | R | 6 |
| GET | `/v1/admin/teacher-applications` | Approval queue | Staff:teacher.approve | T-admin | – | 6 |
| POST | `/v1/admin/teacher-applications/{id}:decide` | Approve or reject | Staff:teacher.approve | T-admin | R | 6 |
| POST | `/v1/teacher/batches` | Create a batch and join code | Role:teacher | T-write | R | 6 |
| GET | `/v1/teacher/batches` | My batches | Role:teacher | T-read | – | 6 |
| POST | `/v1/teacher/batches/{id}/join-code:rotate` | Rotate join code | Role:teacher (batch) | T-write | – | 6 |
| GET | `/v1/teacher/batches/{id}/members` | Batch roster | Role:teacher (batch) | T-read | – | 6 |
| DELETE | `/v1/teacher/batches/{id}/members/{user_id}` | Remove a member | Role:teacher (batch) | T-write | – | 6 |
| POST | `/v1/batches:join` | Student joins by code (consent required if under 18) | User | T-write | R | 6 |
| POST | `/v1/batches/{id}:leave` | Leave a batch | User | T-write | – | 6 |
| POST | `/v1/teacher/batches/{id}/tasks` | Set a written task with rubric questions | Role:teacher (batch) | T-write | R | 6 |
| GET | `/v1/batches/{id}/tasks` | Tasks for a student or teacher | Role:batch.member | T-read | – | 6 |
| POST | `/v1/tasks/{task_id}/submissions` | Start a submission for a task item | User (member) | T-write | R | 6 |
| POST | `/v1/submissions/{id}/pages` | Confirm an uploaded page (resumable per page) | Owner | T-upload | R | 6 |
| POST | `/v1/submissions/{id}:submit` | Submit; starts AI drafting | Owner | T-write | R | 6 |
| GET | `/v1/submissions/{id}` | Student view: status, released marks, labels | Owner | T-read | – | 6 |
| GET | `/v1/teacher/review-queue` | Triage-ordered queue (photo, draft, evidence) | Role:teacher | T-read | – | 6 |
| GET | `/v1/teacher/submissions/{id}` | Submission with pages, AI drafts and evidence | Role:teacher (batch) | T-read | – | 6 |
| POST | `/v1/teacher/submissions/{id}/marks` | Confirm or change each part; teacher mark is final | Role:teacher (batch) | T-write | R | 6 |
| POST | `/v1/teacher/tasks/{id}:release` | Release marks to students | Role:teacher (batch) | T-write | R | 6 |
| GET | `/v1/marking/accuracy` | Published accuracy per subject and part | Public | T-read | – | 6 |
| POST | `/v1/admin/marking/accuracy-reports` | Publish an accuracy report | Staff:ai.publish | T-admin | R | 6 |

### 3.10 Gamification (GAM)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/rewards/summary` | XP total, level, progress to next, daily goal ring, streak, freezes | User | T-read | – | 3 |
| PUT | `/v1/rewards/daily-goal` | Change daily goal (applies next Dhaka day) | User | T-write | – | 3 |
| GET | `/v1/rewards/history` | Ledger entries (paginated) | User | T-read | – | 3 |
| GET | `/v1/leaderboards` | Board: `period`, `track`, `audience`, `audience_id`; top 100 + own rank and 5 neighbours | User | T-read | – | 3 |
| GET | `/v1/friends` | Friend list | User | T-read | – | 3 |
| GET | `/v1/friends/code` | My friend code and QR payload | User | T-read | – | 3 |
| POST | `/v1/friends` | Add friend by code (mutual link) | User | T-write | O | 3 |
| DELETE | `/v1/friends/{user_id}` | Remove friend | User | T-write | – | 3 |
| GET | `/v1/admin/gam/flags` | Anti-abuse review | Staff:gam.review | T-admin | – | 3 |
| POST | `/v1/admin/gam/flags/{user_id}:decide` | Hide or restore on boards | Staff:gam.review | T-admin | R | 3 |
| POST | `/v1/admin/gam/rules` | Publish a new rule version | Staff:gam.rules | T-admin | R | 3 |
| POST | `/v1/admin/gam/boards:rebuild` | Rebuild boards from the ledger | Staff:gam.rules | T-admin | R | 3 |
| GET | `/v1/badges` | Badges earned and available | User | T-read | – | 7 |
| GET | `/v1/leagues/current` | Current league cohort and standings | User | T-read | – | 7 |
| GET | `/v1/challenges` | Active challenges and progress | User | T-read | – | 7 |
| POST | `/v1/challenges/{id}:join` | Join a challenge | User | T-write | O | 7 |
| POST | `/v1/share-cards` | Render a share card (result, streak, rank) with referral link | User | T-write | R | 7 |
| POST/PATCH | `/v1/admin/gam/badges[/{code}]`, `/v1/admin/gam/challenges[/{id}]` | Manage badges and challenges | Staff:gam.rules | T-admin | R | 7 |
| GET | `/v1/store/items` | Rewards store | User | T-read | – | 9 |
| POST | `/v1/store/redemptions` | Spend coins | User | T-write | R | 9 |
| POST/DELETE | `/v1/follows/{user_id}` | Follow or unfollow | User | T-write | – | 9 |
| GET | `/v1/team-leagues/current` | Institution team league | User | T-read | – | 9 |

### 3.11 Exams (EXAM) and control room (OPS-01a)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/exams` | Listing: live, mock, model test, past paper, institution | User | T-read | – | 5 |
| GET | `/v1/exams/{id}` | Detail, countdown, registration state | User | T-read | – | 5 |
| POST | `/v1/exams/{id}/registrations` | Register. Free exams: `confirmed` with the attempt created. Paid exams: a seat `reserved` for 30 min with an order to pay, `confirmed` on capture, auto-refund if the reservation lapsed or the exam is full. Response `{registration_id, status, attempt_id?, reserved_until?, order?}` | User | T-write | R | 5 |
| POST | `/v1/exams/{id}/attempts:start` | Start or take over an attempt; returns exam token, paper URL, `ends_at` | User | T-write | R | 5 |
| POST | `/v1/exams/{id}/attempts/current/token` | Refresh the exam token (checks epoch and current extensions) | User | T-auth | – | 5 |
| GET | `/v1/exams/{id}/attempts/current/status` | Status object polled every 60 s (`ends_at`, extensions) | User | T-read | – | 5 |
| GET | `/v1/exams/{id}/attempts/current/acknowledged` | Acknowledged answers for recovery on a new device | User | T-read | – | 5 |
| POST | `/v1/ingest/attempts/{attempt_id}/batches` | Answer batch number `seq` (per-attempt batch sequence; one in flight). Accepted only if `seq = acked + 1`; duplicates are re-acked; gaps get `seq_gap`. Ack `acked_through = seq` after SQS confirms | ExamToken | T-ingest | R (`seq`) | 5 |
| GET | `/edge/time` | Edge clock for offset measurement | Public | edge | – | 5 |
| GET | `/edge/exams/{id}/key` | Paper key, only at or after start | ExamToken | edge | – | 5 |
| POST | `/v1/exams/{id}/practice-attempts` | Start a mock, model test or past-paper exam (non-live, same attempt model) | User | T-write | R | 5 |
| POST | `/v1/exam-attempts/{id}/answers` | Save answers for non-live exams (through API, not ingest) | Owner | T-answer | R | 5 |
| POST | `/v1/exam-attempts/{id}:submit` | Submit a non-live attempt or early-submit a live one | Owner | T-write | R | 5 |
| GET | `/v1/exam-attempts/{id}/result` | Result (provisional or final; precomputed for live) | Owner | T-read | – | 5 |
| GET | `/v1/exam-attempts/{id}/review` | Per-question solutions after `solution_unlock_at` | Owner | T-content | – | 5 |
| POST | `/v1/exam-attempts/{id}:reattempt` | Re-attempt (practice only, never rank) | Owner | T-write | R | 5 |
| GET | `/v1/exams/{id}/merit` | Published merit list (scope filter). Returns first name and institution only; opted-out users are masked except to themselves (NFR-07) | User | T-read | – | 5 |
| POST/PATCH | `/v1/admin/blueprints[/{id}]` | Blueprint builder (CMS-06) | Role:content.exam | T-admin | R | 5 |
| POST/PATCH | `/v1/admin/exams[/{id}]` | Create and schedule exams, audiences, publish times | Staff:exam.manage | T-admin | R | 5 |
| POST | `/v1/admin/exams/{id}:freeze-paper` | Generate and encrypt bundles (T−24 h) | Staff:exam.manage | T-admin | R | 5 |
| GET | `/v1/admin/exams/{id}/control-room` | Live count, ack latency, queue depth, incidents, close progress | Staff:exam.control | T-admin | – | 5 |
| POST | `/v1/admin/exams/{id}:extend` | Extend time (exam or attempt); cumulative ≤ `EXAM_MAX_EXTENSION_MIN`; moves `result_publish_at` | Staff:exam.control | T-admin | R | 5 |
| POST | `/v1/admin/exams/{id}:void` | Void a live or finished exam with a reason (paper leak, outage): unpublishes merit, notifies candidates, refunds fees | Staff:exam.publish | T-admin | R | 5 |
| POST | `/v1/admin/exams/{id}/questions/{qv_id}:invalidate` | Invalidate a question; triggers rescore | Staff:exam.control | T-admin | R | 5 |
| POST/PATCH | `/v1/admin/exams/{id}/incidents[/{iid}]` | Incident log | Staff:exam.control | T-admin | R | 5 |
| GET | `/v1/admin/exams/{id}/late-answers` | Late-answer cases | Staff:exam.control | T-admin | – | 5 |
| POST | `/v1/admin/exams/{id}/late-answers/{case_id}:decide` | Accept or reject a late answer | Staff:exam.control | T-admin | R | 5 |
| POST | `/v1/admin/exams/{id}/merit-snapshots` | Build a merit snapshot | Staff:exam.publish | T-admin | R | 5 |
| POST | `/v1/admin/merit-snapshots/{id}:publish` | Publish or unpublish | Staff:exam.publish | T-admin | R | 5 |
| GET | `/v1/admin/merit-snapshots/{id}/export` | Downloadable list (CSV/PDF) | Staff:exam.publish | T-admin | – | 5 |
| POST | `/v1/exam-attempts/{id}/integrity-events` | App-switch, blur, screenshot logs (batched) | Owner | T-write | O | 8 |
| GET | `/v1/admin/exams/{id}/anomalies` | Anti-cheat review console | Staff:exam.integrity | T-admin | – | 8 |
| POST | `/v1/admin/anomalies/{id}:decide` | Clear or confirm | Staff:exam.integrity | T-admin | R | 8 |
| POST | `/v1/exam-attempts/{id}/written-answers/{qv_id}/pages` | Written exam page upload | Owner | T-upload | R | 8 |
| GET | `/v1/admin/exams/{id}/written-queue` | Examiner queue for written exam answers (EXAM-10) | Staff:exam.examiner | T-admin | – | 8 |
| POST | `/v1/admin/written-answers/{id}/marks` | Examiner marks per rubric part (AI drafts as suggestions) | Staff:exam.examiner | T-admin | R | 8 |
| GET | `/v1/exam-series` | Series and packages | User | T-read | – | 8 |
| GET | `/v1/exam-series/{id}/standings` | Cumulative leaderboard | User | T-read | – | 8 |
| GET | `/v1/certificates` | My certificates | User | T-read | – | 8 |
| GET | `/v1/certificates/verify/{code}` | Public verification (QR target) | Public | T-read | – | 8 |
| POST/PATCH | `/v1/admin/exam-series[/{id}]` | Manage series | Staff:exam.manage | T-admin | R | 8 |
| POST | `/v1/exam-attempts/{id}/proctor-snapshots` | Proctor snapshot upload (consented) | Owner | T-upload | R | 9 |
| GET | `/v1/predictions` | Admission and job score predictor | User | T-read | – | 9 |
| POST | `/v1/admin/cutoffs:import` | Import historical cut-offs | Staff:exam.manage | T-admin | R | 9 |

### 3.12 Planner and notifications (PLAN)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/countdowns` | Exam countdown per enrolled track | User | T-read | – | 3 |
| GET | `/v1/notifications` | Inbox | User | T-read | – | 3 |
| POST | `/v1/notifications:mark-read` | Mark one, many or all read | User | T-write | – | 3 |
| POST | `/v1/push-tokens` | Register FCM token (APNs in 8) | User | T-write | O | 3 |
| DELETE | `/v1/push-tokens/{id}` | Remove token | Owner | T-write | – | 3 |
| GET/PUT | `/v1/notification-preferences` | Quiet hours, categories | User | T-read / T-write | – | 3 |
| GET/POST/PATCH/DELETE | `/v1/study-plan/items[/{id}]` | Study calendar | User | T-read / T-write | O | 7 |
| GET | `/v1/tracker` | Circulars, admit cards, exam dates, results (`?track=`) | User | T-read | – | 8 |
| PUT/DELETE | `/v1/tracker/{item_id}/follow` | Follow and alert | User | T-write | – | 8 |
| POST | `/v1/eligibility:check` | Eligibility checker from profile and GPA inputs | User | T-read | – | 8 |
| POST/PATCH | `/v1/admin/tracker[/{id}]` | Manage tracker data | Staff:plan.tracker | T-admin | R | 8 |
| POST/PATCH | `/v1/admin/eligibility-rules[/{id}]` | Manage eligibility rules | Staff:plan.tracker | T-admin | R | 8 |
| POST/DELETE | `/v1/channels/{channel}` | Bind WhatsApp or Telegram | User | T-write | O | 9 |
| POST | `/v1/calendar-feed` | Create or rotate iCal feed URL | User | T-write | – | 9 |
| POST | `/v1/webhooks/telegram` | Telegram bot updates (binding, delivery) | Signed | T-webhook | – | 9 |
| GET/POST | `/v1/webhooks/whatsapp` | WhatsApp Cloud API verification and status callbacks | Signed | T-webhook | – | 9 |
| GET | `/v1/calendar-feed/{token}.ics` | iCal feed | Public (token) | T-read | – | 9 |
| POST/PATCH | `/v1/admin/templates[/{code}]` | Manage message templates | Staff:plan.templates | T-admin | R | 3 |

### 3.13 Commerce (PAY)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/products` | Catalogue for a track | Public | T-read | – | 3 |
| GET | `/v1/me/entitlements` | Active entitlements and free quotas | User | T-read | – | 3 |
| POST | `/v1/me/trials` | Start a trial (once per product) | User | T-write | R | 3 |
| POST | `/v1/orders` | Create order (product, coupon); returns provider redirect or SDK payload | User | T-write | R | 6 |
| GET | `/v1/orders/{id}` | Order status ("পেমেন্ট যাচাই হচ্ছে" polling) | Owner | T-read | – | 6 |
| POST | `/v1/orders/{id}/callback` | Client return from bKash or aggregator (triggers verify) | Owner | T-write | R | 6 |
| POST | `/v1/coupons:validate` | Validate a coupon for a product | User | T-write | – | 6 |
| GET | `/v1/me/referral` | My referral code and credits | User | T-read | – | 6 |
| GET | `/v1/me/invoices` | Receipts | User | T-read | – | 6 |
| GET | `/v1/me/invoices/{id}/pdf` | Invoice PDF (signed URL) | Owner | T-read | – | 6 |
| POST | `/v1/store/purchases/google` | Verify Play Billing purchase token | User | T-write | R | 6 |
| POST | `/v1/store/purchases/apple` | Verify Apple IAP transaction | User | T-write | R | 8 |
| POST | `/v1/webhooks/bkash` | bKash IPN via SNS (subscription confirm + notifications) | Signed | T-webhook | – | 6 |
| POST | `/v1/webhooks/aggregator` | SSLCommerz or aamarPay IPN | Signed | T-webhook | – | 6 |
| POST | `/v1/webhooks/google-play` | Real-time developer notifications (Pub/Sub push) | Signed | T-webhook | – | 6 |
| POST | `/v1/webhooks/apple-store` | App Store server notifications v2 | Signed | T-webhook | – | 8 |
| GET | `/v1/admin/orders` | Order and payment search | Staff:pay.read | T-admin | – | 6 |
| POST | `/v1/admin/entitlements` | Manual grant (source `admin`) | Staff:pay.grant | T-admin | R | 6 |
| POST | `/v1/admin/entitlements/{id}:revoke` | Revoke or shorten | Staff:pay.grant | T-admin | R | 6 |
| POST | `/v1/admin/payments/{id}/refunds` | Full or partial refund with reason | Staff:pay.refund | T-admin | R | 6 |
| GET | `/v1/admin/reconciliation/runs` | Runs and exceptions | Staff:pay.finance | T-admin | – | 6 |
| POST | `/v1/admin/reconciliation/uploads` | Upload a settlement file | Staff:pay.finance | T-admin | R | 6 |
| POST | `/v1/admin/reconciliation/exceptions/{id}:resolve` | Resolve an exception | Staff:pay.finance | T-admin | R | 6 |
| POST/PATCH | `/v1/admin/products[/{id}]`, `/v1/admin/coupons[/{id}]`, `/v1/admin/quota-policies[/{id}]` | Manage catalogue, coupons, quotas | Staff:pay.catalogue | T-admin | R | 3 (coupons 6) |
| GET/POST/DELETE | `/v1/me/subscriptions[/{id}]` | Auto-renew subscriptions | User | T-read / T-write | R | 8 |
| POST | `/v1/me/subscriptions/{id}:change` | Upgrade or downgrade with proration quote | Owner | T-write | R | 8 |
| POST | `/v1/family-plans` | Create a family plan | User | T-write | R | 8 |
| POST | `/v1/family-plans/{id}/members` | Add a child | Owner | T-write | R | 8 |
| POST | `/v1/affiliates` | Apply as campus ambassador | User | T-write | R | 8 |
| GET | `/v1/affiliates/me/report` | Attribution and payout report | Role:affiliate | T-read | – | 8 |
| POST | `/v1/admin/affiliate-payouts:run` | Payout run | Staff:pay.finance | T-admin | R | 8 |
| POST/PATCH | `/v1/admin/sponsorships[/{id}]` | Sponsored seat pools | Staff:pay.catalogue | T-admin | R | 9 |
| POST | `/v1/admin/sponsorships/{id}/seats` | Assign sponsored seats | Staff:pay.grant | T-admin | R | 9 |

### 3.14 Parents (PAR)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| POST | `/v1/me/guardian-link-codes` | Child issues a code or QR | User | T-write | R | 8 |
| POST | `/v1/guardian/links` | Parent redeems a code | User | T-write | R | 8 |
| DELETE | `/v1/guardian/links/{id}` | Revoke (either side) | Role:link.party | T-write | – | 8 |
| GET | `/v1/guardian/children` | Linked children | Role:guardian | T-read | – | 8 |
| GET | `/v1/guardian/children/{child_id}/overview` | Study time, streak, exams, scores, rank trend, weak subjects | Role:guardian (link) | T-read | – | 8 |
| GET | `/v1/guardian/children/{child_id}/reports` | Weekly reports | Role:guardian (link) | T-read | – | 8 |
| GET/PUT | `/v1/guardian/children/{child_id}/controls` | Tutor mode lock, time cap, quiet hours | Role:guardian (link) | T-read / T-write | – | 8 |
| GET/POST/DELETE | `/v1/guardian/children/{child_id}/alerts[/{id}]` | Alert rules | Role:guardian (link) | T-read / T-write | O | 9 |

### 3.15 Institutions (INST, P1–P2)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| POST | `/v1/admin/workspaces` | Create an institution workspace | Staff:inst.manage | T-admin | R | 8 |
| GET/PATCH | `/v1/workspaces/{id}` | Workspace and branding | Role:inst.admin | T-read / T-write | – | 8 |
| POST/PATCH | `/v1/workspaces/{id}/branches[/{bid}]` | Branches | Role:inst.admin | T-write | R | 8 |
| POST/DELETE | `/v1/workspaces/{id}/members[/{uid}]` | Teachers and staff | Role:inst.admin | T-write | R | 8 |
| POST | `/v1/workspaces/{id}/batches` | Batches and sections (extends B6 batches) | Role:inst.admin | T-write | R | 8 |
| POST | `/v1/workspaces/{id}/roster:import` | CSV or roll-number import | Role:inst.admin | T-write | R | 8 |
| POST | `/v1/workspaces/{id}/roster/invites` | Invite students | Role:inst.admin | T-write | R | 8 |
| POST | `/v1/roster:claim` | Student claims a roster entry (code) | User | T-write | R | 8 |
| GET/POST | `/v1/workspaces/{id}/seats` | Seat and licence allocation | Role:inst.admin | T-read / T-write | R | 8 |
| POST/PATCH | `/v1/workspaces/{id}/questions[/{qid}]` | Private bank (tenant-scoped QB) | Role:inst.teacher | T-write | R | 8 |
| POST | `/v1/workspaces/{id}/exams` | Batch exam from platform and private bank | Role:inst.teacher | T-write | R | 8 |
| GET | `/v1/workspaces/{id}/exams/{eid}/merit` | Batch merit list | Role:inst.teacher | T-read | – | 8 |
| POST | `/v1/workspaces/{id}/omr-templates` | Generate printable OMR sheet | Role:inst.teacher | T-write | R | 8 |
| POST | `/v1/workspaces/{id}/omr-scans` | Submit a phone OMR scan | Role:inst.teacher | T-upload | R | 8 |
| POST | `/v1/workspaces/{id}/paper-generations` | Print-ready paper PDFs, sets A–D | Role:inst.teacher | T-write | R | 8 |
| GET | `/v1/workspaces/{id}/analytics` | Per batch and student analytics | Role:inst.teacher | T-read | – | 8 |
| POST | `/v1/workspaces/{id}/homework` | Assignments with due dates | Role:inst.teacher | T-write | R | 8 |
| GET | `/v1/me/homework` | Student homework list | User | T-read | – | 8 |
| POST/PATCH | `/v1/workspaces/{id}/listings[/{lid}]` | Marketplace listings | Role:inst.teacher | T-write | R | 9 |
| GET | `/v1/marketplace` | Browse marketplace | User | T-read | – | 9 |
| GET/PUT | `/v1/workspaces/{id}/payout-account` | Payout account | Role:inst.admin | T-read / T-write | – | 9 |
| GET/PUT | `/v1/workspaces/{id}/whitelabel` | Subdomain and theme | Role:inst.admin | T-read / T-write | – | 9 |
| GET | `/v1/whitelabel/{subdomain}/config` | Tenant client config | Public | T-read | – | 9 |
| POST | `/v1/workspaces/{id}/attendance` | Record attendance | Role:inst.teacher | T-write | R | 9 |
| GET/POST | `/v1/workspaces/{id}/fees` | Fee records | Role:inst.admin | T-read / T-write | R | 9 |

### 3.16 Operations (OPS)

| Method | Route | Purpose | Auth | RL | Idem | B |
|---|---|---|---|---|---|---|
| GET | `/v1/admin/audit-log` | Search audit log | Staff:audit.read | T-admin | – | 1 |
| PUT | `/v1/admin/runtime-config/{key}` | Kill switches and min app version | Staff:ops.config | T-admin | R | 1 |
| GET | `/v1/banners` | Active banners for the caller | User | T-read | – | 6 |
| GET | `/v1/notices` | Notices | User | T-read | – | 6 |
| POST/PATCH | `/v1/admin/banners[/{id}]`, `/v1/admin/notices[/{id}]` | Manage | Staff:ops.content | T-admin | R | 6 |
| GET | `/v1/support/config` | Helpdesk widget token, FAQ URL, call and WhatsApp links | User | T-read | – | 6 |
| POST | `/v1/support/widget-token` | Signed identity token for the bought helpdesk | User | T-write | – | 6 |
| GET/PUT | `/v1/admin/feature-flags[/{key}]` | Feature flags and remote config | Staff:ops.config | T-admin | R | 8 |
| POST/PATCH | `/v1/admin/campaigns[/{id}]` | Segmented campaigns | Staff:ops.campaign | T-admin | R | 8 |
| POST | `/v1/admin/campaigns/{id}:send` | Send or schedule | Staff:ops.campaign | T-admin | R | 8 |
| POST/PATCH | `/v1/admin/experiments[/{id}]` | A/B tests | Staff:ops.campaign | T-admin | R | 8 |
| GET | `/v1/admin/bi/{report}` | BI reports (DAU/WAU, funnels, conversion, retention, revenue, AI cost per user) from the S3 log | Staff:ops.bi | T-admin | – | 8 |

---

## 4. Endpoint counts

Counted from §3: one per method per route, where a combined row such as `POST/PATCH … [/{id}]` counts each method once.

| Build | Operations introduced |
|---|---|
| 1 | 47 |
| 2 | 38 |
| 3 | 57 |
| 4 | 22 |
| 5 | 35 |
| 6 | 56 |
| 7 | 62 |
| 8 | 79 |
| 9 | 57 |
| **Total** | **453** |

The traceability check in [`16_feature_traceability_matrix.md`](16_feature_traceability_matrix.md) recounts exact operations from the OpenAPI snapshot once code exists.

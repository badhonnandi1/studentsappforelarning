# 00 · Architecture review

**Date:** 2026-11-27 · **Part A** reviews the existing documents and the skeleton before planning and records the corrections this plan adopts. **Part B** records the independent multi-perspective review of this plan and the fixes applied.

Sources reviewed: [`system-design-v2.md`](../system-design-v2.md) (source of truth), [`architecture-review.md`](../architecture-review.md), [`project-summary.md`](../project-summary.md), [`product-strategy.md`](../product-strategy.md), [`market-validation.md`](../market-validation.md), [`system-design.md`](../system-design.md) (v1), `initial_plan.md` (identical to v1 apart from 3 lines), [`features.md`](../../features.md), `README.md`, the current `backend/` folder skeleton (commit `acb5cbb`), the previous runnable skeleton (commit `860f996`), and the user's FastAPI starter conventions.

---

# Part A: Review of existing documents

## A.1 What we are building

A study platform for Bangladesh (Class 6–12, university admission, government and bank jobs). It has 180 requirements across 17 modules: 93 P0, 67 P1, 20 P2. Two pillars ship at launch, the **AI tutor** and **gamification**. The launch differentiator is **teacher-checked marking of handwritten creative-question answers, with published accuracy** (product strategy, D9).

| Fact | Value | Source |
|---|---|---|
| Architecture | FastAPI modular monolith, PostgreSQL 17, Redis, Postgres job queue, SQS only for exam answers, S3 Parquet event log | v2 §0.2, §2 |
| Deployables | `api`, `workers`, `ai-gateway`, `exam-ingest`, `exam-consumers` (+ a Cloudflare edge Worker) | v2 §2.1 |
| Server modules | 16 (OFF is client-only) | v2 §2.4, skeleton |
| Learning core | One attempt record feeds the notebook, progress, XP, streak, tutor context and analytics, written in one transaction | v2 §1.2, C8 |
| Exam path | Device-first durability, one batch in flight, SQS acknowledgement, two-phase close, contiguity check | v2 §6, C1 |
| AI | One provider at P0 (Claude Haiku/Sonnet/Opus 5.5 tiers), canonical cache without personal data, cited answers, eval gates | v2 §4, C5–C7 |
| Gamification | Append-only ledger, Dhaka-date streaks with effective time, Redis leaderboards rebuilt from the ledger | v2 §5, C12 |

## A.2 Module interactions and foundations

| Category | Modules | Reason |
|---|---|---|
| **Foundational** (everything depends on them) | NFR (outbox, jobs, idempotency, rate limits), AUTH, OPS audit, core/shared | Every write needs auth, audit or events |
| **Content foundation** | TAX → QB → CMS | Practice, exams and AI need published, verified versions |
| **Learning core** | PRAC + ANL + GAM (same transaction), PAY entitlements | v2 C8 |
| **Built on the core** | AI (needs answer context, quotas, content), EXAM (needs content, entitlements, epoch, PLAN, GAM) | |
| **Largely independent** | COM moderation, PLAN transport, PAY gateways, OPS console | Can be built in parallel once AUTH exists |
| **Tenant-dependent (P1)** | INST, PAR | Need RLS and roster models |

**Scalability challenges:** exam ingest (up to 30k req/s at 200k candidates), the answer transaction at 100k concurrent learners, outbox relay throughput, AI provider token limits, leaderboard fan-out, rescoring popular questions.

**Special security or concurrency needs:** the answer transaction, reward idempotency, streak settlement, payment capture, blind key verification, exam takeover epoch, refresh-token rotation, social account linking, tenant isolation, the tutor exam lock (fail closed).

## A.3 Inconsistencies found and corrections adopted

Each row says what is inconsistent, what it would cost if it were coded as written, and the correction this plan adopts. **S** marks items that need supervisor approval (collected in A.5).

| # | Inconsistency | Consequence if coded as written | Correction adopted |
|---|---|---|---|
| 1 | **Cross-user answer-id 409.** v2 §3.2 and the §8.2 security gate say the same `answer_id` from another user returns 409. But C4 makes uniqueness `(user_id, id)`, and the table must be hash-partitioned by `user_id`, so a global unique index is impossible. | Either a global unique index (blocks partitioning, the largest table becomes unsplittable) or a gate that can never pass | User B's request with A's id is stored as B's own new answer. No row of A is ever read or returned. The gate is restated as "a replayed answer id never returns another user's data". **S-1** |
| 2 | **"24-hour repeat" vs "per Dhaka date"** (v2 §5.1). The XP table says the same question earns nothing again "within 24 hours". The anti-farming list says per-day limits, "the 24-hour repeat rule" included, use the effective Dhaka date. | Two developers implement different rules; the §5.5 tests become ambiguous | Rolling 24 h on `effective_at`, backed by index `(user_id, question_id, effective_at)`. The cap and the daily goal stay per Dhaka date. **S-2** (D6 refinement) |
| 3 | **"Backend and database before frontend"** (this assignment) vs v2 §8.1 parallel client stream H, the week-2 device spike (OFF-01) and the week-6 end-to-end slice | The device-performance risk (2 GB Android, 30 MB, PWA 170 KB) surfaces only after all nine builds. If the spike fails, a Kotlin exam screen adds 3–4 weeks, discovered late. The week-28 launch is no longer reachable with P0 backend at 15–21 weeks plus client work. | Follow the assignment. Recommend that the supervisor allow the week-2 spike as throwaway validation, not frontend implementation. The API is frozen per build via the OpenAPI snapshot so client work can start the moment the rule is relaxed. **S-4** |
| 4 | **100,000+ concurrent users** (this assignment) vs v2's planning numbers: 6,000 concurrent outside exams in year 1, 200,000 concurrent exam candidates as a design ceiling, launch cap 20,000 | Overbuilding for 100k on day one, or claiming 100k without evidence | [`17`](17_scalability_and_performance.md) models both workloads. Stages 1k → 100k+ have triggers and load tests. Nothing is claimed without a benchmark. |
| 5 | **Grading output fields.** AI-07b requires "score, rubric breakdown, missing points, model answer, rewrite suggestions". v2 `grading_parts(marks, evidence, flags)` has no fields for missing points or rewrite suggestions (v1 had them). | AI-07b is not met | `ai.grading_parts` adds `missing_points jsonb`, `rewrite_suggestions`, `model_answer_ref`. |
| 6 | **Exam blueprint structure.** v2 describes sections and counts. market-validation §2.1 shows that SSC 2027+ needs "answer N of M" choice, open-ended section types (practical, financial statement, descriptive), different splits per subject and year, CQ parts of 3 or 4 with varying marks, and papers shared by SSC and Dakhil. | Fixed enums and a fixed 4-part CQ would need a redesign for the first real blueprint | `exam.section_types` (reference table, open-ended), `blueprint_sections.answer_required_count`, blueprints per subject × syllabus version, variable `cq_subparts`, `qbank.paper_tracks`. |
| 7 | **D1 fallback lost.** v1 said that if the textbook licence is refused, QB-12 concept notes move to P0. v2's D1 default drops that consequence. | If D1 fails, the tutor has only explanations and question ids to ground on; AI-02 "notes" grounding is weaker than v1 intended | Conditional scope change recorded in [`20`](20_risk_register.md). `qbank.concept_notes` exists from B2 (needed for QB-04 anyway), so pulling QB-12 forward is content work plus a small B2 extension. **S-6** |
| 8 | **Money representation.** v2 §3.1 uses integer poisha; the starter's `Money` is a 2-decimal `Decimal`. | Mixed representations and rounding drift in ledgers | **Decided by the user (2026-11-27): integer poisha** (`bigint *_poisha`, `Poisha` type). Decimal conversion only inside payment-provider adapters. |
| 9 | **Repository layer.** This assignment asks for repositories; the starter forbids repository classes. | Either a class-based layer contradicting house conventions, or SQL in services | `internal/repositories/` holds plain async query functions (no classes). Services own transactions. **S-3** (adds a folder to the reviewed skeleton) |
| 10 | **import-linter config size.** The `860f996` skeleton used 18 contracts in 393 lines, breaking the 200-line rule; it also did not stop imports of another module's root package. | Rule violation; boundary gaps | A compact `.importlinter` (layers + exam-ingest isolation) plus `scripts/check_boundaries.py` (grimp, about 120 lines) for module-internal privacy and cycle detection. |
| 11 | **DB driver.** The deleted skeleton used psycopg 3; the starter uses asyncpg. | Inconsistent conventions | asyncpg (starter convention). PgBouncer transaction mode needs `statement_cache_size=0`, or PgBouncer ≥ 1.21 with `max_prepared_statements` (verify in staging). |
| 12 | **KaTeX at publish time** (v2 §0.3) is a JavaScript library | A pure-Python worker cannot render it | A small Node CLI renderer in the worker image only, called by the render job. Documented in B2. |
| 13 | **Exam XP and streak** (v2 §5.1: +30 XP, "submits one exam" counts the day) | Writing GAM inside the exam path would put Postgres on ingest or the consumer hot path | Awarded asynchronously from `exam.submitted` by a GAM consumer, idempotent on the attempt. |
| 14 | **"17 modules"** in v2 §2.1 for `api` | OFF has no server code | 16 server modules; OFF backend support (min app version, lite payloads, offline pack API, APNs/Apple IAP) lives in NFR, PRAC, PLAN, PAY. |
| 15 | **"Four deployables"** in v2 §2.1 text vs five in its table and the skeleton | Confusion in infra planning | Five Python deployables plus the edge Worker; a sixth (`realtime`) arrives in B9 for PRAC-13. |
| 16 | **Social sign-in scope.** AUTH-01 lists only Google (plus phone OTP and optional email/password). The user asked on 2026-11-27 to add Facebook and similar sign-in methods. | Undocumented requirement if not recorded | Recorded scope change: Google and Facebook in B1, Apple in B8 (with iOS), email/password in B8 (still deferred per C20), all behind one `SocialProvider` interface with safe account-linking rules. Traced as AUTH-01 sub-rows; the ID count stays 180. |
| 17 | **Partition keys and uniqueness.** v2 lists `reward_transactions.idempotency_key UNIQUE` (global). With hash partitioning by `user_id`, a global unique is impossible. | Migration failure, or an unpartitioned ledger | Unique `(user_id, idempotency_key)`. Keys already embed per-user source ids, so this is equivalent. |
| 18 | **Exam answers in mastery.** v2 says Mistake Notebook and mastery come from `attempt_answers` and that exam attempts record into it, but exam answers live in `exam_answers_latest` | Exam answers missing from mastery, or Postgres writes on the ingest path | After final scoring, a job copies scored exam answers into `attempt_answers` (context `exam_live`) in chunks. Answers are not copied for exams whose results are not final. |
| 19 | **Telemetry volume.** `POST /v1/events:batch` into the outbox would put client screen-time events in the OLTP database | Outbox bloat at Stage 4 | Telemetry goes through a capped Redis stream to S3 Parquet, bypassing Postgres. It is best-effort and never a learning record. |
| 20 | **Facebook age rule.** Facebook requires users to be 13 or older; Class 6 students can be 11 | Under-13 social sign-ups | Server-side age gate. Date of birth is required before any account is created, by any method (a pending sign-up token; Part B R-24). Under-13 users use phone OTP. All under-18 sign-ups still need guardian consent (NFR-07). |

## A.4 Things checked and found consistent

- v2 §9 coverage maps all 180 IDs with matching priorities; v2 §11 describes the check. Re-checked in [`16`](16_feature_traceability_matrix.md).
- The review findings (architecture-review §3, §6) all map to C1–C25 and D1–D9.
- `tenant_id` from day one, attempts pinned to versions, idempotency per user, the outbox from the first answer, blind two-person verification, the server-enforced exam lock and minors' privacy defaults are all retained ("do not simplify", architecture-review §6).

## A.5 Decisions requiring supervisor approval

| # | Decision | Default in this plan |
|---|---|---|
| S-1 | Restate the cross-user answer-id gate (A.3 #1) | "Never returns another user's data" |
| S-2 | 24-hour repeat rule on rolling `effective_at` (A.3 #2) | Rolling 24 h |
| S-3 | Add `internal/repositories/` and `internal/providers/` to the module template (A.3 #9) | Added |
| S-4 | Allow the week-2 device spike despite "backend first" (A.3 #3) | Recommended, not assumed |
| S-5 | Facebook sign-in in P0, Apple with iOS (A.3 #16) | Approved by the user 2026-11-27; supervisor to confirm |
| S-6 | If D1 fails, pull QB-12 concept notes into P0 (A.3 #7) | Conditional |
| S-7 | Effort and timeline: 113–158 backend person-weeks; P0 backend in 15–21 weeks with about 4.5 backend FTE ([`04`](04_backend_master_plan.md) §6.3) | Needs staffing confirmation |
| S-7 is superseded by S-12 (Part B). | |
| S-8 | Open v2 decisions D1–D9 remain open; this plan builds on their defaults | v2 §10 defaults |
| S-9 – S-12 | Added by the independent review; see Part B | |

**Approval status (2026-11-27).** Supervisor sign-off on S-1 – S-12 is **still pending**. Build 1 was started on the user's instruction on 2026-11-27, using the defaults in the table above. Any decision the supervisor later changes is applied as a follow-up change to Build 1.

---

# Part B: Independent review of this plan

**Method.** A separate agent that had not written any part of the plan reviewed the finished documents read-only, from seven perspectives: principal architect, senior database engineer, senior FastAPI engineer, security engineer, SRE, QA lead and engineering manager. It returned 32 findings (2 critical, 10 high, 17 medium, 3 low), each with a quoted section reference. Every finding was accepted and fixed in the documents named in the last column. None was rejected.

**Verdict before fixes:** "strong, unusually thorough, but not ready to build as written". R-03 and R-04 would have broken the plan's own Build 1 and Build 3 gates, and R-01, R-02 and R-09 were exam-correctness and availability defects.

| ID | Sev. | Perspective | Finding (short) | Resolution | Fixed in |
|---|---|---|---|---|---|
| R-01 | Critical | DBA, SRE | `seq` meant a batch in 01 and an answer in B5; the contiguity check compared consumers with themselves | `seq` is the per-attempt **batch** number. Ingest acknowledges only N = acked + 1 and records `acked_through` in the exam Redis, in every SQS message and in the submit marker. The contiguity check uses the maximum of the ingest, message, marker and client evidence, plus an aggregate count of sent messages. | 01 §4.14, 09 |
| R-02 | Critical | Architect, SRE | The exam token expired before an extended end; per-attempt extensions were cut off by the exam-wide close | Token `exp` = `ends_at` + maximum extension + grace, with a token-refresh endpoint. The close is driven by the latest effective attempt end, and extensions move `result_publish_at`. | 09, 14 |
| R-03 | High | Architect | Dependency cycles (CMS ⇄ PRAC, INST ⇄ AI, AUTH ⇄ all, EXAM → PRAC) | Authorization moved to `core.security`. OPS and PLAN became near-leaves. Rescoring is a PRAC job triggered by `correction.created`. INST → AI only. Deletion and exam-answer copies travel by events. The graph was redrawn and checked acyclic (17 nodes, 39 edges). | 04 §4–§5, 07, 10, 12, 13 |
| R-04 | High | FastAPI | Queue names and priorities in the build docs violated the `platform.jobs` CHECK | One canonical queue list in `core/jobs/queues.py`; the migration generates the CHECK from it; priority −100..100; a contract test | 01 §3.1/§4.1, 05–13, 17 |
| R-05 | High | QA | Four different key formats for the same reward, so XP could be granted twice | One public key-builder module with golden tests, plus a test that the transaction, repair, rebuild and consumer paths produce the same keys | 01 §4.11/§5.2, 07, 11, 13 |
| R-06 | High | DBA, QA | Streak length was never recomputed; 00:00–06:00 answers broke streaks; the 72 h offline window collided with 06:00 finality; exam streak days waited for final scoring | Lazy settlement of earlier days before counting today, with the length recomputed. From B7, days settle provisionally at 06:00 and finally at the end of the 72 h window (**S-9**). `exam.submitted` is emitted at submit or provisional close. | 01 §4.11, 07, 09, 11 |
| R-07 | High | Security | Staff SSO and 2FA were promised "for B6" but never planned | Staff OIDC SSO with enforced MFA in **B1**; admin routes reject tokens not issued through SSO | 05, 14 §3.2, 18 |
| R-08 | High | Security, DBA | `execute_requested` was dropped from the payment CHECK, so a crash could execute twice; a second capture on a paid order took money silently | Persist `execute_requested` before calling Execute. Record a `duplicate_captured` state, then auto-refund it and open a reconciliation exception. | 01 §4.12, 10 |
| R-09 | High | SRE | Exam ingest depended on a shared Redis; losing it blocked every candidate | A dedicated exam Redis (`noeviction`, AOF, Multi-AZ). Chunked recovery resends. A one-time resync when the ack ledger is missing. The "safe to lose" claim in 01 was corrected. | 01 §3.17, 09, 17, 19 |
| R-10 | High | Security (minors) | Streamed model text reached children before moderation and verification | Release by sentence only after incremental moderation. Under-18 users and free-form answers are buffered until verification, with progress events; canonical hits stream immediately (**S-11**). | 08, 17, 18 |
| R-11 | High | Eng. manager | B8 and B9 were under-estimated, and the calendar was total effort ÷ FTE | B8 re-estimated at 24–32 pw and B9 at 26–36 pw (OMR and voice start as spikes). Total 138–186 pw. The calendar comes from the critical path with review weeks: about 44–57 weeks, P0 about 24–31. | 04 §6.3 |
| R-12 | High | SRE | Every load test ran in B9, after all the design was frozen | A Stage-4 synthetic benchmark of the answer transaction, relay, `processed_events` and board fan-out at the B3 exit, plus consumers with learner overlap at the B5 exit | 07 §F, 09, 17 |
| R-13 | Medium | DBA | 16 hash partitions were too few for about 11B rows a year | 64 hash partitions on `attempt_answers` and `reward_transactions` | 01 §1.2/§4, 03, 07, 17 |
| R-14 | Medium | DBA | FKs on the hottest insert paths cause KEY SHARE and MultiXact contention, and block a later cluster split | No FKs on `attempt_answers` and `reward_transactions`; references are validated in the application. The exception is listed in §1.1. | 01 §1.1, 02 |
| R-15 | Medium | SRE | Conflicting rates between 01 and 17; `processed_events` WAL not modelled | 17 §2 is the single rate table; dedupe is one row per (consumer, relay batch) | 01 §4.1/§5.11, 17 |
| R-16 | Medium | FastAPI | Leaderboard ZINCRBY was not atomic with the dedupe | A per-board Lua script with a ledger-position marker | 01 §5.2 R20, 07 |
| R-17 | Medium | SRE | A p95 2 s lag target was impossible with a 2–10 s relay loop | Relay polls every 250 ms while busy and 1 s when idle, on a direct connection; target restated as p95 ≤ 5 s | 01 §5.4, 05, 17 |
| R-18 | Medium | FastAPI | `dedupe_key` stopped working once completed jobs were deleted | Completed jobs that have a dedupe key are kept until `dedupe_until`, then removed by retention | 01 §3.1/§4.1/§5.3, 03, 05 |
| R-19 | Medium | DBA | Coupon violation aborted the capture transaction; re-mark order violated the unique index; `RETURNING (old value)` is not valid PostgreSQL | SAVEPOINT around the coupon redemption; clear the old final grading first; `SELECT … FOR UPDATE` then `UPDATE` for the XP cap | 01 §5.2, 07, 10 |
| R-20 | Medium | DBA | Registration cap used `count(*)` under an advisory lock; a paid candidate could hit "exam full" with no refund | Conditional counter on `exams.registered_count`; seat reserved before payment; auto-refund on lapse | 01 §3.10, 09, 14 |
| R-21 | Medium | Architect | An exam could not be voided once live | `voided` status reachable from live through published, with audit, notifications, refunds and merit unpublish | 01 §4.14, 09, 14 |
| R-22 | Medium | Security | A missing Redis key unlocked the tutor during an exam | `exam.is_user_exam_locked` is the authority (running-exam registry plus registration check); the Redis key is a cache; fail closed | 08, 09 |
| R-23 | Medium | DBA | HNSW filters apply after the scan, so recall drops on selective filters | pgvector ≥ 0.8 iterative scans, tenant partial indexes or exact search, filtered queries in the search gate | 01, 08, 12, 18 |
| R-24 | Medium | Security | DOB was optional, so under-13 Facebook accounts could be created and later locked out | DOB is required before any account is created (pending sign-up token); unlinking requires a verified phone | 05, 18 |
| R-25 | Medium | Security | No control for phone-number recycling or SIM swap | Dormant re-verification, a second factor or support check on phone change, guardian re-confirmation, step-up OTP for sensitive actions | 05, 18 |
| R-26 | Medium | QA | The ingest isolation contract pointed at a path the build doc did not use | `app.modules.exam.ingest` is a public subpackage; paths aligned | 05, 09, 15 |
| R-27 | Medium | QA | Critical-path coverage globs missed exam consumers, the repair job and webhook processing | Package-level globs, RLS policy tests included | 15 |
| R-28 | Medium | Architect | B6 wrote to mastery, which arrives in B7; stale B6 deletion wording | B6 emits `marking.teacher_checked`, consumed in B7; wording fixed | 10, 11 |
| R-29 | Medium | Eng. manager, QA | B7 statistics need real history that will not exist before launch | Synthetic-data acceptance criteria now, with a post-launch calibration gate | 11, 12, 20 |
| R-30 | Low | Security | Offline packs expose keys on rooted phones | Accepted risk: per-user watermarking, canary items, 5 packs per day, expiry with the entitlement | 11, 18, 20 |
| R-31 | Low | QA | Test phone range did not match the phone regex | Reserved block `+88017000000xx`, allowed only in test and dev | 05, 15 |
| R-32 | Low | All | Small contradictions (answer contexts, "never updated", body limits, `passed`/`succeeded`, freeze scope, provider `free`, k6 vs Python, empty Part B) | Canonical values chosen and aligned in every document; this Part B written | several |

**Decisions added to A.5 by the review:**

| # | Decision | Default |
|---|---|---|
| S-9 | Streak settlement becomes provisional at 06:00 and final at the end of the tolerance window once offline packs exist (B7), which reintroduces freeze returns. This changes v2 C12. | Adopted from B7; P0 is unchanged (final at 06:00) |
| S-10 | DOB is required before any account exists, for every sign-in method | Adopted |
| S-11 | Under-18 and free-form tutor answers are buffered until verification, so first-token latency becomes "first verified sentence" | Adopted; latency gates re-measured in B4 |
| S-12 | Effort re-baselined to 138–186 pw, about 44–57 calendar weeks (P0 about 24–31) | Needs staffing decision |

**Residual uncertainty.** Nothing in this plan has been measured. In particular:
- ingest throughput per instance;
- answer-transaction capacity on the chosen RDS size;
- provider token-per-minute limits;
- Bangla OCR and marking accuracy;
- bKash settlement APIs.

All of these remain **[Needs evidence]**. They are scheduled for measurement at the B3 and B5 exits and in the v2 milestone tests.


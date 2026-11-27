# Build 5 · Live exam engine

| Item | Value |
|---|---|
| Build | 5 of 9 |
| Status | Planned (not started) |
| Depends on | Build 3 complete (QB versions, PRAC attempt records, PAY entitlements, PLAN notifications, GAM ledger); Build 1 (auth device sessions with `exam_epoch`, outbox, jobs, audit); Build 4's exam-lock **contract** (`exam/contracts/lock.py`). It can start in parallel with B4 if the contract file is merged first. |
| Effort | 13–18 backend person-weeks, plus platform engineer time for SQS, the load-balancer pre-warm and the load generators ([`04`](04_backend_master_plan.md) §6.3) |
| Feature IDs | EXAM-01, EXAM-02, EXAM-03, EXAM-04, EXAM-04a, EXAM-05, EXAM-06, EXAM-07, EXAM-08; CMS-06; OPS-01a; ANL-02; NFR-01, NFR-01a, NFR-02 (exam part), NFR-03 (zero-loss part); CMS-04a (exam rescoring part) |

---

## 0. How to run this build

1. **Read, in order:**
   - [`README.md`](README.md)
   - [`04_backend_master_plan.md`](04_backend_master_plan.md)
   - this document
   - [`01_database_design.md`](01_database_design.md) §3.10 (all `exam` tables marked B5), §1.2 (partitioning), §3.17 (exam keys), §5.1–§5.3 (exam rows, R12, R13)
   - [`14_api_contracts.md`](14_api_contracts.md) §3.11 and §3.7 (exam history)
   - [`17_scalability_and_performance.md`](17_scalability_and_performance.md) (the exam workload model)
   - [`system-design-v2.md`](../system-design-v2.md) §6 in full, including §6.1 load, §6.2 trace and §6.3 zero loss
2. **Preconditions:**
   - `main` is green.
   - B3's exit criteria are met.
   - `exam/contracts/lock.py` exists (from B4), or is created by this build's first step if B4 has not merged yet. Coordinate so only one PR adds it.
   - Localstack provides SQS and S3. A Cloudflare account with `wrangler` is needed for edge deploys to staging only; local tests use Miniflare.
3. **Branch:** `build/05-exam-engine`.
4. **Commands:**
   - `scripts/check.sh`
   - `cd edge && npm ci && npm run check` (eslint, tsc, vitest, line check)
   - `uv run pytest -m concurrency tests/modules/exam`
   - load harness (staging only): `k6 run tests/load/exam_live.js` (k6 scripts in JavaScript under `backend/tests/load/`; verification with `uv run python tests/load/exam_verify.py`)
5. **Stop rule.** Stop at §F. Do not build anti-cheat (EXAM-09*, B8), written exams (EXAM-10, B8), series or certificates (B8), or any client screen.

---

## A. Overview

| Item | Detail |
|---|---|
| Name | Live exam engine |
| Objective | Run every exam type on one attempt model. Live exams have a synchronised start, a server-authoritative deadline, answers durable before acknowledgement, a two-phase close, a contiguity check, deferred merit, and results precomputed for the publish rush. The control room can extend time and invalidate questions. |
| Business value | National mock exams are the main acquisition and retention event for SSC, HSC and admission candidates. NFR-01 is the hardest P0 requirement. |
| Technical value | Proves the isolated ingest path (`exam-ingest` has no Postgres), SQS durability, consumer idempotency and the fault-injection harness at 20,000 candidates (v2 week-8 milestone; settles D5 and option S12). |
| Modules | EXAM (primary); OPS (control-room UI contract, audit); ANL (exam history); CMS (correction to exam rescoring); GAM (exam XP through events); PLAN (reminders, result pushes); PAY (fee entitlement check); AUTH (device session epoch); QB (paper versions) |
| Complexity | 5/5 |
| Effort | 13–18 pw |

**Features**

| ID | Delivered |
|---|---|
| EXAM-01 / CMS-06 | Blueprints: open-ended section types, N-of-M choice, counts per chapter, difficulty and type, marks, negative marking, section timers, optional sections, pass marks, per subject × syllabus year; admin builder APIs |
| EXAM-02 | Exam types: mock (auto-generated from blueprint), fixed model test, live, previous-year paper, institution/batch (restricted audience created by ops) |
| EXAM-03 | Server support for the exam UI: paper bundle contents (palette, sections, timers, calculator flag), `ends_at`, status object |
| EXAM-04 | Listing, registration (fee through PAY entitlement), reminders T−24h/T−1h/T−10min, countdown, paper locked until start |
| EXAM-04a | Synchronised start via edge key release; late entry 15 min; auto-submit at end (no submit call needed); `result_publish_at`; `solution_unlock_at` |
| EXAM-05 | Local-first answers synced in contiguous batches; resume after disconnect, app kill or new device; server-authoritative timer |
| EXAM-06 | Merit: national, district, institution (labelled self-reported), group; tie-breaks; versioned snapshots; publish/unpublish; export |
| EXAM-07 | Result page data: score, correct/wrong/skipped, negative-mark loss, time, rank, percentile, topper and average, per-question solutions after unlock |
| EXAM-08 | Re-attempts feed practice and mastery, never rank; review mode |
| OPS-01a | Control room: live participants, ack latency, queue depth, consumer lag, close progress, incident log, extend time, invalidate question |
| ANL-02 | Exam history with score and rank trends |
| NFR-01 / NFR-01a | Pre-generated encrypted papers on CDN; answers through a queue; merit as a batch job; load test before every major exam; launch cap 20,000 (C17) |
| NFR-02 (exam) | Provisional score without rank within 5 s (C3); instant results for non-live exams p95 < 5 s at 2,000 concurrent submits |
| NFR-03 (zero loss) | Acknowledged ⇒ scored; contiguity check blocks publication on any gap |
| CMS-04a (exam) | Correction or invalidation leads to rescore, a new merit snapshot and ops approval before republication |

**Risks and blockers**

| Risk | Mitigation |
|---|---|
| Ingest throughput per instance unmeasured (1,500 req/s assumed) | Measure in the step C15 benchmark. The result sets pre-scaling and is recorded in [`17`](17_scalability_and_performance.md). |
| Postgres upsert rate at the ceiling (~19k rows/s) | 500-message batches, `COPY`-style multi-row inserts. The rehearsal measures it. Exam tables can move to a dedicated instance (01 §5.9). |
| SQS outage during an exam | Ingest returns 503; clients keep answers locally; the control room extends time; the runbook in [`19`](19_devops_and_deployment.md) |
| Clock skew on devices | Deadline is the server `ends_at`; edge time offset; device clock never trusted |
| D7 closing policy not yet confirmed | Built on the v2 default: late window to end + 10 min, provisional at end + 60 s, merit at end + 15 min or later. All values are in `exams` columns and settings, not code. |
| SSC 2028 blueprint split unconfirmed (market-validation §2.1) | Blueprints are data; seed a draft blueprint marked `status='draft'` |

---

## B. Database

### B.1 Tables to create (01 §3.10)

| Migration | Tables | Notes |
|---|---|---|
| `b05_01_exam_blueprints` | `exam.section_types` (seeded: `cq`, `short`, `mcq`, `practical`, `financial_statement`, `descriptive`), `exam.blueprints`, `exam.blueprint_sections`, `exam.blueprint_rules` | `CHECK (answer_required_count <= item_count)`; `CHECK (negative_mark_per_wrong >= 0)` |
| `b05_02_exam_exams` | `exam.exams`, `exam.exam_audiences` | `CHECK (ends_at > starts_at)`; for `kind='live'`: `CHECK (result_publish_at >= ends_at + interval '15 minutes')` and `CHECK (solution_unlock_at >= ends_at)`; `registered_count int NOT NULL DEFAULT 0` with `CHECK (registered_count >= 0 AND (registration_cap IS NULL OR registered_count <= registration_cap))`; `status` CHECK includes `voided`; ix `(status, starts_at)` |
| `b05_03_exam_papers` | `exam.exam_papers`, `exam.exam_paper_items` | uq `(exam_id, lang, set_code)` |
| `b05_04_exam_registrations_attempts` | `exam.registrations`, `exam.exam_attempts` | `registrations.status` CHECK IN (`reserved`, `confirmed`, `released`, `cancelled`), `reserved_until timestamptz NULL`, ix `(status, reserved_until) WHERE status='reserved'`; uq `(exam_id, user_id)` on registrations; uq `(exam_id, user_id, attempt_no)`; ix `(exam_id, status)`; `exam_starts_on date NOT NULL` copied from the exam |
| `b05_05_exam_answer_log` | `exam.exam_answer_batches` P, `exam.exam_answers_latest` P (RANGE monthly on `exam_starts_on`) | Create the current and next 3 months; register with partition maintenance (archive and drop after 12 months, per 01 §5.6) |
| `b05_06_exam_scoring` | `exam.scoring_configs`, `exam.exam_results`, `exam.close_runs`, `exam.late_answer_cases` | ix `(exam_id, phase, score DESC)` on results; uq `(exam_id, phase)` on close runs |
| `b05_07_exam_merit` | `exam.merit_snapshots`, `exam.merit_entries` | uq `(exam_id, version)`; ix `(user_id)` on entries for exam history |
| `b05_08_exam_control` | `exam.incidents`, `exam.time_extensions` | — |

### B.2 Tables modified

| Table | Change | Migration |
|---|---|---|
| `cms.corrections` | Uses its existing `exam_cursor` and `merit_republish_required`; no DDL | — |
| `practice.attempt_answers` | No DDL. Exam answers are copied by the PRAC consumer of `exam.scored` with `context IN ('exam_live','exam_practice','exam_reattempt')` and `exam_attempt_id` set. These values are already in the B3 CHECK (canonical list in 01 §3.9), so no constraint swap is needed. | — |

### B.3 Relationships

- `exams.blueprint_id` → `blueprints` (FK, RESTRICT); `exams.paper_id` → `qbank.papers` (cross-schema FK allowed, immutable).
- `exam_paper_items.question_version_id` → `qbank.question_versions` (FK).
- `registrations.user_id`, `exam_attempts.user_id` → `identity.users` (FK).
- `exam_attempts.device_session_id` is a plain uuid (AUTH-owned, mutable).
- `exam_answer_batches` and `exam_answers_latest` have no FK to attempts. They are partitioned and high volume; attempt existence is checked at token issue, and the contiguity check is the integrity proof.
- `exam_results.attempt_id` → `exam_attempts` (FK; same schema, not partitioned).
- `merit_entries.snapshot_id` → `merit_snapshots` (FK).

### B.4 Transaction and integrity requirements

| Operation | Rule |
|---|---|
| Register | One transaction. Check the window and audience. Reserve a seat with a conditional counter, with no advisory lock and no `count(*)`: `UPDATE exam.exams SET registered_count = registered_count + 1 WHERE id = :id AND registered_count < registration_cap RETURNING registered_count`. No row returned means 409 `exam_full`.<br>• **Free exam:** insert the registration as `confirmed`, plus the attempt (`attempt_no=1, kind='ranked', status='not_started'`), and write `exam.registered` to the outbox.<br>• **Paid exam (`fee_product_id` set):** insert the registration as `reserved` with `reserved_until = now + 30 min` and return the order to pay. On `payment.captured`, confirm it, create the attempt and write `exam.registered`.<br>• **Lapse:** the `exam.release_reservations` job (every minute) moves lapsed reservations to `released` and decrements `registered_count` in the same transaction. A payment captured for a released or full reservation enqueues `pay.auto_refund` and writes a reconciliation note; the candidate is never left paid without a seat. |
| Void | `Staff:exam.publish` with a reason. Allowed from `live`, `closing`, `provisional`, `final` or `published` to `voided`. One transaction: status change, audit row, unpublish every merit snapshot, outbox `exam.voided`. Consumers notify candidates through PLAN and enqueue fee refunds through PAY. |
| Start or take over | One transaction: lock the attempt `FOR UPDATE`. If `device_session_id` differs, increment `epoch` and set the new session (the takeover requires a fresh sign-in, `auth_time` within 10 min in the access token). Set `started_at` once. After commit, write exam-Redis `exam_lock:{user}` (cache only; the lock authority is the registry, R-22), `exam:epoch:{attempt}` and `exam:status:{exam}`. |
| Consumer batch | Steps, one transaction, then delete the SQS messages after commit:<br>1. Insert batches `ON CONFLICT DO NOTHING`. `seq` is the per-attempt **batch** number.<br>2. Upsert latest `ON CONFLICT (attempt_id, question_version_id, exam_starts_on) DO UPDATE … WHERE (excluded.seq, excluded.change_no) > (exam_answers_latest.seq, exam_answers_latest.change_no)`. The highest batch wins; within one batch, the highest `change_no` wins.<br>3. Update `exam_attempts.max_acked_seq = GREATEST(max_acked_seq, message.acked_through)`. This is advisory only, used for monitoring and as one input to the contiguity evidence; one statement per attempt in the batch.<br>4. If the message is a submit marker, write `exam.submitted` to the outbox in the same transaction (R-06). |
| Close phases | Each phase is a `close_runs` row; a phase may start only if the previous phase's row is `passed` (state machine in code, uq `(exam_id, phase)`). |
| Final scoring | Runs only after `contiguity` passed. Results are upserted with `phase='final'`. |
| Merit snapshot | A REPEATABLE READ transaction reads `exam_results`; snapshots are immutable; publishing changes only `status`. |
| Invalidate question | Insert a new `scoring_configs` version (audited), then enqueue a rescore. If a snapshot is published, the republish needs approval (`cms.corrections.merit_approved_by`). |

---

## C. Backend implementation

### C.1 Steps in dependency order

1. **Settings:**
   - `exam_answer_queue_backend` (memory, sqs), `exam_answer_queue_url`, `exam_dlq_url`
   - `exam_token_private_key`, `exam_token_public_key` (Ed25519, separate from the user JWT keys)
   - `exam_grace_minutes` (10), `exam_provisional_delay_s` (60), `exam_merit_min_delay_min` (15), `exam_late_entry_min` (15)
   - `exam_max_extension_min` (`EXAM_MAX_EXTENSION_MIN`, default 60): the ceiling on extensions; it also bounds the exam token `exp`
   - `exam_redis_url`: the **dedicated exam Redis** (R-09); `exam_reservation_hold_min` (30)
   - `r2_bucket`, `r2_endpoint`, `kms_key_id`
   - `ingest_max_batch_answers` (200)

   The prod validator refuses the memory queue (as in the skeleton).
2. **Models and repositories** for all B5 tables.
3. **Blueprints** (EXAM-01, CMS-06): validation (sections sum to `total_marks`; N ≤ M; rule counts ≤ section counts) and admin routes.
4. **Exams and audiences** (EXAM-02):
   - CRUD and the status machine `draft → scheduled → paper_frozen → live → closing → provisional → final → published`.
   - `cancelled` is reachable from any state before `live`.
   - `voided` is reachable from `live`, `closing`, `provisional`, `final` or `published`, by `Staff:exam.publish` with a reason. A void is audited, unpublishes merit, notifies candidates and refunds fees; this covers a paper leak or a regional outage (R-21).
5. **Paper assembly:**
   - Mock auto-generation from the blueprint. Per rule, select published versions under the node subtree (`curriculum` ltree via `tax.subtree_ids`), filtered by difficulty and type, excluding retired items, deterministic with a seed.
   - Fixed papers from `qbank.papers`.
6. **Paper freeze** (NFR-01a), triggered by admin or a scheduled job at `freeze_at` (default T−24h):
   - Render a bundle per language: JSON with question HTML, media references, sections, timers, calculator flag. **No answer keys.**
   - Compress with brotli.
   - Encrypt with AES-256-GCM using a fresh per-exam data key.
   - The key is wrapped by KMS (`key_ciphertext`); the plaintext key is pushed to the Cloudflare Worker KV only at T−5 min.
   - Upload the bundle to R2 under an unguessable path (`papers/{exam_id}/{random128}.bin`); record the sha256 and byte size.
7. **Registration and the exam token** (EXAM-04):
   - A confirmed registration creates the attempt. Paid exams reserve a seat first (§B.4).
   - The exam JWT:
     - Claims: `aud=exam-ingest`, `sub=user`, `attempt_id`, `sid`, `epoch`, `exam_id`, `starts_at`, `ends_at`.
     - `exp = ends_at + exam_max_extension_min + grace`. An extension therefore never invalidates tokens mid-exam.
     - Signed with the exam key.
     - The token is only a credential. Ingest enforces the **real** deadline from `exam:status:{exam}` (which includes exam-wide extensions) and the attempt's own `ends_at` (per-attempt extensions).
     - `POST /v1/exams/{id}/attempts/current/token` re-issues the token: it checks the epoch and the current extensions. Clients call it after a takeover, on 401 `token_expired`, or when an extension is announced in an ack.
   - Reminders are enqueued as jobs with dedupe keys `exam_reminder:{exam}:{user}:{t}` for T−24h ("sign in now" push), T−1h and T−10min, sent through `plan.notify` in cohorts.
8. **Start and takeover** (EXAM-04a, AUTH-02): epoch increment, plus Redis `exam_lock:{user_id}` in the exam Redis (TTL to `ends_at + max extension + grace`).

   **Tutor lock authority (R-22).** The public function `exam.is_user_exam_locked(user_id)` decides; the Redis key is only a fast-path cache. A missing key never unlocks.
   - **Running-exam set.** `exam/lock_registry.py` keeps an in-process set of running exams (`live`, `closing`), refreshed every 15 s from Postgres.
   - **Registration membership.** Membership in those exams is cached per user for 15 s.
   - **Decision.** Locked if the user is registered in a running exam. The `exam_lock` key short-circuits to locked when present.
   - **Failure.** If Postgres and Redis are both unreachable, fail closed for every user in the last-known registry.
   - **Packaging.** The registry is part of EXAM's public surface (`app.modules.exam.lock_registry`), imported by `ai-gateway` without touching `internal`.
9. **Edge Worker** (`edge/`):
   - `GET /edge/time`
   - `GET /edge/exams/{id}/key`: verify the exam token signature (Ed25519 public key in a Worker secret), check `edge_now >= starts_at` and `exp`, return the key from KV.
   - The key push job writes KV at T−5 min through the Cloudflare API.
10. **Ingest** (`exam-ingest`, code in the public subpackage `app.modules.exam.ingest`; all Redis access goes to the dedicated exam Redis):
    - **Definition of `seq` (R-01).** `seq` is the per-attempt **batch** sequence number, contiguous from 1. A batch carries every answer not yet acknowledged. Each answer has `question_version_id`, `response`, `device_effective_at` and `change_no`, where `change_no` is a per-question counter the device increments on every change. Answers have no per-answer seq.
    - **Token and epoch.** Verify the token with the public key only. Check epoch freshness from `exam:epoch:{attempt}`.
    - **One in flight.** Enforce one in-flight batch with `SET exam:inflight:{attempt} NX PX 10000`.
    - **Acceptance rule** (`acked` = `exam:acks:{attempt}`):
      - `seq == acked + 1`: new; send it.
      - `seq ≤ acked`: a duplicate; idempotent re-ack with the current `acked_through`, nothing sent.
      - `seq > acked + 1`: 409 `seq_gap` with `acked_through`.
    - **Missing ack ledger (R-09).** If `exam:acks` is missing (exam Redis lost), accept the client's claimed `acked_through` **once**, using it as `acked`, and record a `resync` flag in the message and in `exam:resync:{attempt}`. The client is never forced to resend from seq 1. The contiguity check still catches real loss.
    - **Send and ack.**
      - `SendMessage` to SQS. The message carries `attempt_id`, `exam_id`, `seq`, `exam_starts_on`, the answers, `is_submit_marker`, `acked_through` (= `seq` after this send) and the `resync` flag.
      - Only after SQS returns success: `SET exam:acks:{attempt} = seq` and `INCR exam:sent:{exam_id}` (new sends only), then reply `{acked_through: seq, ends_at, server_time}`.
    - **Submit marker.** The submit marker is a normal batch (`is_submit_marker: true`) that also carries the client's final `acked_through`.
    - **Recovery resend.** A recovering client may split its unacknowledged answers into consecutive batches of ≤ 200 answers each (`seq`, `seq+1`, …), sent one at a time.
    - **Late rule.** The deadline is the attempt's effective `ends_at`: `exam:status:{exam}` plus any per-attempt extension. Answers whose `device_effective_at > ends_at` are accepted, flagged `is_late`, and not auto-scored. Batches after `ends_at + grace` are refused with 410 and a body pointing to the control-room evidence path.
    - **SQS failure.** 503 with `Retry-After: 2`.
11. **Consumers** (`exam-consumers`): long-poll SQS (10 messages × 50 receives per loop → 500 per transaction), the transaction from §B.4, delete on commit, DLQ after 5 receives. Metrics: lag and age of the oldest message.
12. **Non-live exams** (mock, model test, past paper): `POST /v1/exams/{id}/practice-attempts`; answers via `POST /v1/exam-attempts/{id}/answers` (API path, idempotent per `(attempt_id, question_version_id, client_seq)` into `exam_answers_latest`); submit gives instant scoring (p95 < 5 s).
13. **Close and scoring (scheduler job `exam.close_tick` every 15 s).** All phase times use `close_base = max(effective ends_at over the exam's attempts)`: exam-wide `ends_at` plus exam-wide extensions, or a later per-attempt extension. They never use the original `ends_at` (R-02).
    - (a) At `close_base + 60 s`: provisional scoring from `exam_answers_latest` (non-late answers only), with results `phase='provisional'`.
      - If `provisional_score_enabled`, precompute `exam:result:{attempt}` with `provisional: true` and no rank, and push "provisional score ready" to early-submitters.
      - Attempts that auto-ended without a processed submit marker get `exam.submitted` written to the outbox here (R-06).
    - (b) At `close_base + grace` (10 min): hard close. Mark attempts closed; ingest stops accepting.
    - (c) Drain: wait until SQS `ApproximateNumberOfMessages` + `NotVisible` = 0 **and** the DLQ = 0 for 3 consecutive checks. If the DLQ is not empty, open an incident and block.
    - (d) **Contiguity (R-01).**
      - **Per attempt:** compute `A = max(exam-Redis exam:acks:{attempt}, highest acked_through in any delivered message (exam_attempts.max_acked_seq), acked_through in the submit marker, client-reported acked_through from status polls and the final flush (recorded by the status endpoint in exam:client_ack:{attempt}))`. The batch log must contain every seq 1..A (`count(DISTINCT seq) = A AND min(seq) = 1 AND max(seq) >= A`).
      - **Aggregate:** `count(DISTINCT (attempt_id, seq))` in the exam's log must equal `exam:sent:{exam_id}`.
      - **On failure:** any gap or mismatch writes `close_runs.details.gaps[]`, opens an incident and blocks publication.
      - **If the exam Redis ledger was lost** (missing keys or `resync` flags), the check runs on the message, marker and client evidence alone, and an incident note records the degraded evidence.
    - (e) Final scoring: apply the key, the `scoring_configs` overrides and invalidations, negative marking, and section N-of-M (best N by marks if more were answered **[Rule]**, configurable). Results get `phase='final'`. Write `exam.scored` to the outbox. The PRAC consumer `prac.record_exam_answers` (a PRAC job, so EXAM never imports PRAC; 04 §4) copies the scored answers into `practice.attempt_answers` in batches of 5,000, idempotent on `answer_id = uuid5(attempt_id, question_version_id)`. It reads them through the EXAM public function `exam.scored_answers(attempt_ids)`. `exam.submitted` was already emitted at the submit marker or in phase (a).
    - (f) Merit at `max(result_publish_at − 5 min, end + 15 min)`: snapshot with ranks national, district (profile), institution (profile, `institution_label='self_reported'`), group. Tie-break: higher score → fewer wrong → less time used → earlier `last_answer_received_at` (server receipt). Percentile = 100 × (N − rank) / (N − 1).
    - (g) Precompute every attempt's result JSON into Redis `exam:result:{attempt}` before `result_publish_at`; cohorted pushes over 5 min.
14. **Results and review:** the result endpoint reads Redis first, falling back to Postgres; review is gated by `solution_unlock_at`; topper and average from the snapshot; re-attempt creates `attempt_no ≥ 2`, `kind='reattempt'`, excluded from merit.
15. **Control room** (OPS-01a):
    - Aggregates: participants (Redis HyperLogLog `exam:live:{exam}` of attempt ids seen in ingest, a proposed key), ack latency histogram (ingest metrics), SQS depth, consumer lag, close-run progress, incidents.
    - Extend time updates `exams.ends_at` or the attempt's `ends_at`, `time_extensions` and the exam-Redis `exam:status`. It propagates through every ack and the 60 s status poll.
      - The total extension per exam or attempt is capped at `exam_max_extension_min`, so existing tokens stay valid.
      - The extension also moves `result_publish_at` (and `solution_unlock_at` if it would precede the new end) forward, keeping `result_publish_at ≥ close_base + 15 min` (PA-C6).
      - The close phases follow the new `close_base`.
    - Invalidate question creates a new scoring config, a rescore and an approval flow.
16. **Exam rescoring from CMS corrections:** consumes `question.corrected` and finds exams whose papers contain the old version. If final, writes a new scoring config with a key override, rescores, creates a new snapshot as `draft`, sets `merit_republish_required`, and waits for `POST /v1/admin/corrections/{id}:approve-merit`.
17. **GAM and streak consumers** (extend `tests/contract/test_reward_key_paths.py` with the exam consumer path): GAM job `gam.exam_submitted` awards +30 XP for live exams (key `xp:live_exam_submitted:{attempt_id}`, built by `gam.contracts.reward_keys`) and +20 for a mock's first attempt of the paper per day (key `xp:mock_submitted:{paper_or_exam_id}:{dhaka_date}`; already unique per user because the ledger key is `(user_id, idempotency_key)`), and counts the streak day (exams_submitted += 1). The effective date is the submission time in Dhaka. `exam.submitted` is emitted when the consumer processes the submit marker, or at provisional close for auto-ended attempts. It never waits for final scoring, so a contiguity incident cannot cost a candidate their streak (R-06). XP and the streak day depend only on this event, never on score.
18. **ANL-02** exam history endpoint: reads `exam_results` (final) + `merit_entries` for the user via EXAM's public function `exam.history_for(user_id, enrolment)`; ANL owns the route and the trend computation.
19. **Load harness and fault injection** (step C15 benchmark first, then the 20k scenario).
20. **Runbooks** referenced from [`19`](19_devops_and_deployment.md): pre-scale, exam freeze, SQS failure, DLQ non-empty, gap found.

### C.2 Folder changes

```
backend/src/app/modules/exam/internal/{models,repositories,services,schemas,routes,jobs,events,consumers,scoring,merit,papers}/
backend/src/app/modules/exam/ingest/        # PUBLIC subpackage (R-26): imported by entrypoints/exam_ingest
backend/src/app/modules/exam/lock_registry.py  # PUBLIC: tutor-lock authority (R-22)
backend/src/app/entrypoints/exam_ingest/{app.py,deps.py}
backend/src/app/entrypoints/exam_consumers/{main.py,loop.py}
backend/tests/modules/exam/{unit,integration,api,concurrency,db,isolation}/
backend/tests/load/{exam_live.js, exam_fault_injection.js, exam_clients.js, exam_verify.py}   # k6 scripts (JavaScript)
edge/                         # NEW TypeScript project
  package.json  tsconfig.json  wrangler.toml  .eslintrc.cjs
  src/{index.ts, time.ts, key.ts, token.ts}
  test/{time.test.ts, key.test.ts, token.test.ts}
  scripts/check-lines.mjs
```

`app.modules.exam.ingest` is a public subpackage, so the entry point never imports `internal` and the layering rule holds. It must import only `core.settings`, `core.redis` (exam Redis client), `core.logging`, `core.security.exam_token`, the queue adapter and `exam/contracts` (pydantic only). This is enforced by `.importlinter` (forbidden: `sqlalchemy`, `asyncpg`, `alembic`, `app.core.db`) and by the subprocess `sys.modules` test.

### C.3 Files

**Exam module: models, repositories**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `exam/internal/models/blueprints.py` | `SectionType`, `Blueprint`, `BlueprintSection`, `BlueprintRule` | 110 |
| `exam/internal/models/exams.py` | `Exam`, `ExamAudience`, `ExamPaper`, `ExamPaperItem` | 130 |
| `exam/internal/models/attempts.py` | `Registration`, `ExamAttempt` | 90 |
| `exam/internal/models/answers.py` | `ExamAnswerBatch`, `ExamAnswerLatest` (partitioned; `__table_args__` with `postgresql_partition_by`) | 70 |
| `exam/internal/models/results.py` | `ScoringConfig`, `ExamResult`, `MeritSnapshot`, `MeritEntry`, `CloseRun`, `LateAnswerCase` | 150 |
| `exam/internal/models/control.py` | `Incident`, `TimeExtension` | 50 |
| `exam/internal/repositories/blueprints.py` | CRUD, rule queries | 100 |
| `exam/internal/repositories/exams.py` | Listing (cursor), status transitions with row lock, audience checks | 140 |
| `exam/internal/repositories/attempts.py` | Registration and attempt insert, lock, epoch bump, current attempt | 130 |
| `exam/internal/repositories/answer_log.py` | Batch insert (multi-row), latest upsert with seq guard, max_acked update, contiguity SQL | 160 |
| `exam/internal/repositories/results.py` | Results upsert (bulk), merit `COPY`, snapshot reads, history | 160 |
| `exam/internal/repositories/control.py` | Incidents, extensions, late cases | 90 |

**Exam module: services**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `exam/internal/services/blueprint_service.py` | Validate and save blueprints; versioning (`version` increments; exams pin a version) | 150 |
| `exam/internal/services/exam_admin.py` | Create and schedule exams; audiences; publish times; state machine guards; audited | 170 |
| `exam/internal/services/listing.py` | Learner listing and detail (audience-filtered, entitlement flags) | 110 |
| `exam/internal/services/registration.py` | Register: cap, window, audience, entitlement, attempt creation, reminders | 150 |
| `exam/internal/services/attempt_start.py` | Start and takeover, epoch, token issue, Redis lock and status, current-attempt status object, acknowledged-answers recovery | 160 |
| `exam/internal/services/non_live.py` | Practice attempts for mock, model test and past paper; API-path answers; submit → instant score | 160 |
| `exam/internal/services/result_service.py` | Result read (Redis first), review gating, re-attempt | 140 |
| `exam/internal/services/control_room.py` | Aggregates, extend time, incidents, late-answer decisions | 170 |
| `exam/internal/services/invalidation.py` | Invalidate question; correction-driven rescore; approval gate | 140 |
| `exam/internal/services/history.py` | `history_for(user, enrolment)` (public) | 70 |

**Papers, scoring, merit**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `exam/internal/papers/assemble.py` | Mock generation from blueprint rules with a seed; fixed paper loading | 160 |
| `exam/internal/papers/bundle.py` | Render a bundle (no keys), brotli, sha256 | 120 |
| `exam/internal/papers/crypto.py` | AES-256-GCM encrypt; KMS wrap and unwrap (adapter with a local fake) | 100 |
| `exam/internal/papers/storage.py` | R2 upload (S3 API), unguessable path, presigned GET for the bundle (15 min before start) | 80 |
| `exam/internal/papers/freeze_job.py` | Job `exam.freeze_paper`; the key push job `exam.push_key_to_edge` at T−5 min | 120 |
| `exam/internal/scoring/score_attempt.py` | Pure function: answers, key, config → score, correct, wrong, skipped, negative loss, N-of-M | 150 |
| `exam/internal/scoring/provisional.py` | Phase (a) runner in chunks of 1,000 attempts | 110 |
| `exam/internal/scoring/close_runner.py` | Phase state machine (a)–(g) driven by `exam.close_tick` | 180 |
| `exam/internal/scoring/drain_check.py` | SQS and DLQ emptiness ×3 | 70 |
| `exam/internal/scoring/contiguity.py` | Contiguity SQL runner and gap report | 90 |
| `exam/internal/scoring/final_scoring.py` | Phase (e): bulk score, results upsert, PRAC copies, outbox | 170 |
| `exam/internal/merit/ranker.py` | Pure ranking with tie-breaks and scopes; percentile | 150 |
| `exam/internal/merit/snapshot.py` | Snapshot build (REPEATABLE READ), publish/unpublish, export (CSV, plus PDF via the B6 renderer later; CSV in B5) | 150 |
| `exam/internal/merit/precompute.py` | Redis `exam:result:{attempt}` precompute; cohorted notification enqueue | 120 |

**Ingest and consumers**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `exam/ingest/queue.py` | `AnswerBatchQueue` protocol, `InMemoryAnswerBatchQueue`, `SqsAnswerBatchQueue` (aioboto3/aiobotocore `send_message`) | 110 |
| `exam/ingest/validate.py` | Token verify (public key), epoch check, one-in-flight, batch `seq` acceptance rule (new, duplicate or gap), `resync` path, payload limits | 150 |
| `exam/ingest/ack_ledger.py` | Exam-Redis ack ledger: `exam:acks`, `exam:sent`, `exam:resync`, idempotent re-ack | 80 |
| `exam/ingest/handler.py` | Batch handler: validate, send (message carries `acked_through`), ack; late flags against the effective deadline; 503 on queue failure; metrics | 140 |
| `exam/ingest/routes.py` | `POST /v1/ingest/attempts/{attempt_id}/batches` | 60 |
| `exam/internal/consumers/receive.py` | Long-poll loop, batch accumulation to 500, visibility extension | 120 |
| `exam/internal/consumers/apply.py` | The consumer transaction (§B.4) | 130 |
| `entrypoints/exam_ingest/app.py` | `create_app("exam-ingest", ready_checks={redis, queue})`, no db | 50 |
| `entrypoints/exam_consumers/main.py` | Worker main with `--check`; graceful SIGTERM (finish the batch, no delete-before-commit) | 80 |
| `core/security/exam_token.py` | Issue (api) and verify (ingest) the exam JWT | 100 |

**Routes, schemas, jobs, events**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `exam/internal/schemas/learner.py` | Listing, detail, registration, start, status, ack recovery, result, review | 170 |
| `exam/internal/schemas/admin.py` | Blueprint, exam, control room, snapshots, late cases | 170 |
| `exam/internal/schemas/ingest.py` | Batch request and ack (shared by ingest; pydantic only) | 70 |
| `exam/internal/routes/learner.py` | Learner routes | 150 |
| `exam/internal/routes/admin_blueprints.py` | Blueprint routes | 70 |
| `exam/internal/routes/admin_exams.py` | Exam admin and freeze | 110 |
| `exam/internal/routes/control_room.py` | Control-room routes | 110 |
| `exam/internal/routes/merit.py` | Merit learner and admin routes | 90 |
| `exam/internal/jobs/scheduling.py` | `exam.close_tick`, `exam.freeze_scheduler`, reminder jobs | 120 |
| `exam/internal/events/handlers.py` | `question.corrected` → invalidation service | 60 |
| `exam/lock_registry.py` (modify; public) | Authority for `is_user_exam_locked`: running-exam set refreshed every 15 s, per-user registration cache (15 s), Redis fast path, fail closed on last-known registry | +60 |
| `exam/internal/services/token_refresh.py` | `POST …/attempts/current/token`: epoch and extension checks, re-issue | 70 |
| `exam/internal/services/void_exam.py` | Void flow: state guard, audit, merit unpublish, `exam.voided` event | 90 |
| `exam/internal/jobs/reservations.py` | `exam.release_reservations` (every minute): release lapsed paid reservations, decrement the counter, refund on late capture | 90 |
| `anl/internal/routes/exam_history.py` + `anl/internal/services/exam_history.py` | ANL-02 route and trend computation | 60 + 100 |
| `gam/internal/events/exam_handlers.py` | `exam.submitted` → XP and streak day | 110 |
| `cms/internal/services/merit_approval.py` | `approve-merit` endpoint service | 70 |
| `prac/__init__.py` + `prac/internal/services/exam_copies.py` | `record_exam_answers()`: idempotent bulk copy into `attempt_answers`, notebook and progress recompute per user | 20 + 150 |

**Edge Worker (TypeScript)**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `edge/src/index.ts` | Router | 40 |
| `edge/src/time.ts` | `{now_ms}` with `Cache-Control: no-store` | 20 |
| `edge/src/token.ts` | Ed25519 JWT verify (WebCrypto), claims check | 90 |
| `edge/src/key.ts` | Key release: time check, KV read, 425 `too_early` before start | 70 |
| `edge/test/*.test.ts` | Vitest with Miniflare | 3 × ~80 |

**Load and fault harness**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `tests/load/exam_clients.js` | k6 simulated client: one batch in flight, random-phase 15 s flush, contiguous batch resend (chunked ≤ 200), reconnect, late answers | 170 |
| `tests/load/exam_live.js` | k6 scenario: lobby, key release, 60 min autosave, end flush | 120 |
| `tests/load/exam_fault_injection.js` | k6 injectors: 1% drop after send (client forgets the ack and must resend), consumer kill, SQS throttle (localstack/fault proxy), 10% reconnect storm, synchronised starts, 2% late between end+1 and end+9, exam-Redis failover (ledger loss → `resync`) | 160 |
| `tests/load/exam_verify.py` | Post-run verification (Python, reads Postgres and the run log): every acknowledged answer scored, gaps found, merit identical across 3 replays (hash of entries) | 120 |
| `tests/load/ingest_benchmark.js` | k6 single-instance ingest throughput benchmark at p99 ack < 500 ms | 90 |

### C.4 Validation rules

**Blueprint**
- Section `marks_per_item × answer_required_count` sums to `total_marks`.
- `answer_required_count ≤ item_count`.
- Each rule's `item_count` sums to the section's `item_count`.
- Nodes belong to the blueprint's syllabus version.
- `negative_mark_per_wrong ∈ [0, marks_per_item]`.

**Exam**
- `starts_at > now + 24h` for live exams at creation, so the freeze can happen. Staff with `exam.manage_override` may shorten this, audited.
- `registration_cap ≤ runtime_config.live_exam_cap`. The default of 20,000 is the C17 launch cap; it is raised only after a rehearsal (the config change is audited).

**Registration**
- Within the window.
- Audience match (`exam_audiences`: institution from the profile, batch membership via INST in B6+, user list).
- Entitlement if `fee_product_id` is set.
- Not already registered (409 `already_registered`).

**Ingest batch**
- `answers` count 1..200.
- `question_version_id` must be in the paper (bundle manifest cached in Redis `exam:paper:{exam}:{lang}`, a proposed key).
- Batch `seq`:
  - `seq == acked + 1` is accepted.
  - `seq ≤ acked` gets an idempotent re-ack.
  - `seq > acked + 1` gets 409 `seq_gap` with the server's `acked_through`, and the client resends from `acked_through + 1`.
  - If the ledger is missing, the client's `acked_through` claim is accepted once (`resync`).
- `change_no ≥ 1` per answer; per question, the latest change wins.
- `response` validated per question type (shared validator from QB contracts).

**Start**
- Not before `starts_at − 15 min` (download window).
- Not after `starts_at + late_entry_min`, unless it is a takeover of an existing started attempt.

### C.5 Caching

| Key | Use |
|---|---|
All keys below live in the **dedicated exam Redis** (R-09). It is a separate ElastiCache replication group: Multi-AZ with automatic failover, `maxmemory-policy noeviction`, AOF `appendfsync everysec`, sized for 200k attempts with headroom. The general Redis (caches, leaderboards, telemetry stream, rate limits) never holds exam keys, so a telemetry burst or an eviction cannot touch the exam path. The exam Redis is still not a system of record: it holds the ack ledger as a durable-enough cache, backed by the `acked_through` carried in every SQS message, the submit marker and client evidence.

| Key | Use |
|---|---|
| `exam_lock:{user_id}` | Fast-path cache of the tutor lock (the authority is `exam.is_user_exam_locked`); TTL `ends_at + max extension + grace` |
| `exam:acks:{attempt}` | Highest acknowledged batch `seq`, written by ingest after SQS success |
| `exam:sent:{exam_id}` | Count of new batches sent to SQS (aggregate contiguity check) |
| `exam:resync:{attempt}` | Set when ingest accepted a client claim after ledger loss |
| `exam:client_ack:{attempt}` | Client-reported `acked_through` from status polls and the final flush |
| `exam:status:{exam}` | `ends_at`, extensions, status (polled; included in acks) |
| `exam:result:{attempt}` | Precomputed result JSON |
| `exam:epoch:{attempt}`, `exam:inflight:{attempt}`, `exam:live:{exam}` (HLL), `exam:paper:{exam}:{lang}` | Epoch check, one in flight, participant count, paper manifest |

### C.6 Error handling

| Condition | Error |
|---|---|
| Start too early | 425 `too_early` |
| Too late, no attempt | 410 `entry_closed` |
| Stale epoch at ingest | 401 `session_taken_over` |
| Second in-flight batch | 409 `batch_in_flight` |
| Gap | 409 `seq_gap` |
| SQS down | 503 `unavailable` + `Retry-After` |
| Not registered | 403 |
| Exam full | 409 `exam_full` |
| Result before publish | 200 with `provisional` data or `{status: "pending", result_publish_at}` |
| Review before unlock | 403 `solutions_locked` |

### C.7 Security

- The exam token is separate from user tokens; the ingest service holds only the public key.
- Papers are encrypted; the key reaches the edge only at T−5 min and is released only at or after start.
- Answer keys never reach the client in a live exam before `solution_unlock_at`.
- Control-room actions require `Staff:exam.control` plus 2FA and are audited.
- Merit APIs never return phone, photo or full name; only `first_name` + institution, respecting `privacy_settings` (opted-out users appear as "শিক্ষার্থী" with rank only to themselves).
- **No deploys from T−24h to T+2h around a major live exam** (≥ 5,000 registrants). CI blocks production deploys when `exams` has such an exam in that window. This is a pipeline check through an admin API (see [`19`](19_devops_and_deployment.md)).

### C.8 Workers and job kinds

`exam.freeze_scheduler` (1 min), `exam.freeze_paper`, `exam.push_key_to_edge`, `exam.reminder`, `exam.close_tick` (15 s), `exam.rescore`, `exam.precompute_results`, `exam.publish_notify_cohort`, `gam.exam_submitted` (GAM consumer), `prac.record_exam_answers` (PRAC consumer of `exam.scored`), `exam.archive_partition` (monthly, after 12 months: Parquet export then drop).

### C.9 Observability

**Metrics:**
- `app_exam_ingest_requests_total{status}`
- `app_exam_ack_latency_seconds`
- `app_exam_sqs_depth`
- `app_exam_consumer_lag_seconds`
- `app_exam_close_phase{exam,phase}`
- `app_exam_contiguity_gaps_total`
- `app_exam_live_participants`

**Live-exam dashboard** (NFR-08) as code.

**Alerts:**
- ack p99 > 2 s for 1 min;
- DLQ > 0;
- consumer lag > 30 s;
- contiguity gap > 0 (page);
- the 99.95% ack SLO during exam windows.

### C.10 Configuration

- Settings from step C1.
- `runtime_config` keys: `live_exam_cap`, `registrations_enabled`.
- Edge secrets: `EXAM_TOKEN_PUBLIC_KEY`, KV namespace `EXAM_KEYS`.

---

## D. API contracts

### D.1 Learner endpoints

| Method / route | Request | Response | Auth / rules | Errors | RL / Idem |
|---|---|---|---|---|---|
| `GET /v1/exams` | `?kind&track_id&status=upcoming|live|past&cursor&limit` | `Page<ExamCard{id, kind, title, starts_at, ends_at, duration_min, fee: Money?, registered, registration_open, seats_left?}>` | User; audience-filtered | – | T-read / – |
| `GET /v1/exams/{id}` | – | `ExamDetail{…card, blueprint_summary{sections[]}, rules{late_entry_min, negative_marking, calculator}, result_publish_at, solution_unlock_at, my_registration?, my_attempts[]}` | User; audience | 404 | T-read / – |
| `POST /v1/exams/{id}/registrations` | `{track_enrolment_id}` | 201 `{registration_id, status: confirmed|reserved, attempt_id? (when confirmed), reserved_until? , order?: {order_id, payable: Money} (paid exams)}` | User; window, cap (conditional counter), audience. A paid exam reserves a seat for 30 min, then pays through PAY; capture confirms. | 409 `already_registered`/`exam_full`, 410 closed | T-write / R |
| `POST /v1/exams/{id}/attempts:start` | `{device_id}` | `{attempt_id, exam_token, token_expires_at, paper: {lang, url, sha256, bytes}, starts_at, ends_at, server_time, acked_through, takeover: bool}` | User registered. Takeover needs `auth_time` ≤ 10 min, else 401 `reauth_required`. | 403, 410 `entry_closed`, 425 `too_early` | T-write / R |
| `POST /v1/exams/{id}/attempts/current/token` | `{device_id}` | `{exam_token, token_expires_at, ends_at, epoch}` | User registered. Checks the epoch (the current device session must own it) and applies current extensions. | 401 `session_taken_over`, 410 after `ends_at + grace` | T-auth / – |
| `GET /v1/exams/{id}/attempts/current/status` | `?acked_through=n` (client-reported; stored as contiguity evidence) | `{status, ends_at, extensions[], server_time, provisional_ready}` | User | 404 | T-read / – |
| `GET /v1/exams/{id}/attempts/current/acknowledged` | – | `{acked_through, answers: [{question_version_id, response, seq, change_no}]}` (from `exam_answers_latest`; `seq` is the batch that carried it) | User (after takeover) | 404 | T-read / – |
| `POST /v1/exams/{id}/practice-attempts` | `{track_enrolment_id, lang}` | 201 `{attempt_id, paper: {questions: [QuestionPayload]}, ends_at}` | User; entitlement | 403, 404 | T-write / R |
| `POST /v1/exam-attempts/{id}/answers` | `{answers: [{question_version_id, response, client_seq, answered_at}] ≤ 50}` | `{saved: n, ends_at}` | Owner; non-live only | 409 (live attempt → use ingest), 410 after end | T-answer / R |
| `POST /v1/exam-attempts/{id}:submit` | `{final_seq?}` | Non-live: `ExamResult` (p95 < 5 s). Live early submit: `{received: true, provisional_at}`; the submit marker is sent through ingest by the client, and this endpoint records intent only. | Owner | 409 already submitted | T-write / R |
| `GET /v1/exam-attempts/{id}/result` | – | `ExamResult{phase: provisional|final, score, total_marks, correct, wrong, skipped, negative_loss, time_used_ms, rank?, percentile?, district_rank?, institution_rank? (+label), group_rank?, topper_score?, average_score?, sections[]}`; `rank` is null while provisional | Owner; before `result_publish_at`, provisional only (if enabled) | 403 | T-read / – |
| `GET /v1/exam-attempts/{id}/review` | – | `Review{items: [{question_payload, your_response, correct_key, explanation_html, marks}]}` | Owner; after `solution_unlock_at` | 403 `solutions_locked` | T-content / – |
| `POST /v1/exam-attempts/{id}:reattempt` | – | 201 `{attempt_id, …}` (`kind=reattempt`, never ranked) | Owner; the original is final | 409 | T-write / R |
| `GET /v1/exams/{id}/merit` | `?scope=national|district|institution|group&scope_id?&cursor` | `Page<MeritRow{rank, first_name, institution_name, institution_label, score}>` + `me{rank, percentile}` | User; published snapshot only | 404 | T-read / – |
| `GET /v1/progress/exam-history` | `?track_enrolment_id&kind?` | `{items: [{exam_id, title, date, score, total, rank?, percentile?}], trends: {score: [..], rank: [..]}}` | User | – | T-read / – |

### D.2 Ingest and edge

**`POST /v1/ingest/attempts/{attempt_id}/batches`**
- **Headers:** `Authorization: Bearer <exam token>`.
- **Request:**
  ```json
  {"seq": 14,
   "client_acked_through": 13,
   "answers": [{"question_version_id": "…", "response": {"selected": ["ga"]},
                "change_no": 2, "device_effective_at": "…Z", "monotonic_since_sync_ms": 512300}],
   "submit_marker": false, "client_sent_at": "…Z"}
  ```
  - `seq` is the per-attempt **batch** number (1, 2, 3 …, contiguous). There is no per-answer seq.
  - `client_acked_through` is the client's last received ack. Ingest uses it only when the exam-Redis ledger is missing (`resync`).
- **Response 200:** `{"acked_through": 14, "ends_at": "…Z", "server_time": "…Z", "late_question_version_ids": […], "duplicate": false}`.
- **Rules:**
  - One batch in flight.
  - Accept `seq == acked + 1`. Re-ack `seq ≤ acked` idempotently (`duplicate: true`). Reject `seq > acked + 1` with `seq_gap`.
  - The batch carries every unacknowledged answer, or, when recovering, consecutive chunks of ≤ 200.
  - The ack comes only after SQS confirms. The SQS message carries `acked_through`.
- **Errors:** 401 (`token_invalid`, `token_expired` → refresh via `…/attempts/current/token`, `session_taken_over`), 409 (`batch_in_flight`, `seq_gap` with `acked_through`), 410 (`after_grace`), 413 (> 200 answers), 422, 503 (`unavailable`).
- **Rate:** T-ingest. **Idempotency:** `(attempt_id, seq)`. A replayed batch returns the same `acked_through`.

**`GET /edge/time`**
- Returns `{"now_ms": 1764…}` with no caching. Public.

**`GET /edge/exams/{id}/key`**
- Bearer exam token.
- Before start: 425 `{"retry_after_ms": n}`.
- After start: `{"key_b64": "…", "alg": "A256GCM"}`.
- Bad token: 401. The token's `exam_id` must match the path.

### D.3 Admin endpoints

| Method / route | Request → response | Auth | Notes |
|---|---|---|---|
| `POST /v1/admin/blueprints` | `{track_id, syllabus_version_id, subject_node_id, name, total_marks, duration_min, pass_marks, negative_mark_per_wrong, calculator_allowed, sections: [{section_type, label, marks_per_item, item_count, answer_required_count, time_limit_min?, is_optional, rules: [{node_id, difficulty_band?, question_type?, item_count}]}]}` → 201 `Blueprint` | Role:content.exam | 422 on any §C.4 rule; Idem R; audited |
| `PATCH /v1/admin/blueprints/{id}` | Partial → creates a new `version` if used by an exam | Role:content.exam | 409 `version_conflict` with `If-Match` |
| `POST /v1/admin/exams` | `{kind, blueprint_id?, paper_id?, title_bn, title_en, audience_kind, audiences?: [..], starts_at, ends_at, late_entry_min, result_publish_at, solution_unlock_at, provisional_score_enabled, registration_opens_at, registration_closes_at, registration_cap, fee_product_id?, freeze_at?}` → 201 | Staff:exam.manage | 422 constraint violations; audited |
| `PATCH /v1/admin/exams/{id}` | Schedule edits only before `paper_frozen`; after that, only `result_publish_at` and `solution_unlock_at` later, and cancel | Staff:exam.manage | 409 `invalid_state` |
| `POST /v1/admin/exams/{id}:freeze-paper` | `{}` → 202 `{job_id}` | Staff:exam.manage | Idempotent per exam |
| `GET /v1/admin/exams/{id}/control-room` | → `{participants, registered, started, submitted, ack_latency: {p50, p95, p99}, sqs: {depth, dlq}, consumer_lag_s, close_runs: [..], incidents: [..], ends_at, extensions}` | Staff:exam.control | Polled every 5 s; reads Redis and CloudWatch metrics through the adapter |
| `POST /v1/admin/exams/{id}:extend` | `{extra_seconds: 60..1800, attempt_id?, reason}` → 200 `{ends_at, result_publish_at}` | Staff:exam.control | Cumulative extension ≤ `exam_max_extension_min` (422 otherwise); moves `result_publish_at`; audited; Idem R |
| `POST /v1/admin/exams/{id}:void` | `{reason}` → 202 `{status: "voided"}` | Staff:exam.publish | From `live`/`closing`/`provisional`/`final`/`published`; unpublishes merit, notifies candidates, refunds fees; audited; Idem R |
| `POST /v1/admin/exams/{id}/questions/{qv_id}:invalidate` | `{mode: "drop"|"award_all"|"override_key", key?, reason}` → 202 `{scoring_config_version}` | Staff:exam.control | Audited; Idem R |
| `POST /v1/admin/exams/{id}/incidents`, `PATCH …/{iid}` | `{kind, severity, description}` / `{resolved_at?, actions?}` | Staff:exam.control | Audited |
| `GET /v1/admin/exams/{id}/late-answers` | → `Page<LateAnswerCase>` | Staff:exam.control | — |
| `POST /v1/admin/exams/{id}/late-answers/{case_id}:decide` | `{decision: "accept"|"reject", reason}` | Staff:exam.control | Accept triggers a rescore of that attempt; audited |
| `POST /v1/admin/exams/{id}/merit-snapshots` | `{}` → 202 | Staff:exam.publish | Refused before the contiguity phase succeeds (409 `not_final`) |
| `POST /v1/admin/merit-snapshots/{id}:publish` | `{action: "publish"|"unpublish"}` | Staff:exam.publish | Refused if a correction requires approval and none is recorded |
| `GET /v1/admin/merit-snapshots/{id}/export` | `?format=csv` → signed URL | Staff:exam.publish | — |
| `POST /v1/admin/corrections/{id}:approve-merit` | `{note}` → 200 | Staff:exam.publish | Audited |

---

## E. Testing

| Type | File | Cases |
|---|---|---|
| Unit | `tests/modules/exam/unit/test_score_attempt.py` | Negative marking 0.25/0.5; skipped; N-of-M best-N; invalidated question (drop vs award all); key override; numeric tolerance |
| Unit | `…/test_ranker.py` | Tie-break chain; equal everything gives the same rank; district, institution and group scopes; percentile edges (N=1) |
| Unit | `…/test_blueprint_validation.py` | Marks sum; N ≤ M; rule sums; node outside the syllabus |
| Unit | `…/test_assemble.py` | Deterministic with a seed; respects counts; excludes retired items; fails cleanly on insufficient items (422 with a shortfall per rule) |
| Unit | `…/test_bundle_crypto.py` | Bundle contains no `answer_key` (deep scan); round-trip decrypt; tamper gives an auth-tag failure |
| Unit | `…/test_ingest_validate.py` | Token audience and expiry; stale epoch; batch seq new/duplicate/gap; one in flight; late flag against the effective (extended) deadline; after grace 410; missing ledger → one `resync` accept, second claim refused |
| Unit | `…/test_token_refresh.py` | A 20-min extension: old token still valid (exp bound), refreshed token reflects it; stale epoch refused |
| Unit | `edge/test/*.test.ts` | Key 425 before start using a fake clock; 200 after start; wrong exam id 401; tampered token 401; time endpoint not cached |
| Isolation | `tests/modules/exam/isolation/test_ingest_no_postgres.py` | Subprocess imports `app.entrypoints.exam_ingest.app` and asserts none of `sqlalchemy`, `asyncpg`, `app.core.db` are in `sys.modules`; plus the `.importlinter` contract |
| Integration | `tests/modules/exam/integration/test_live_flow.py` | Full flow with the memory queue and a frozen clock: register, freeze, start, batches, end, provisional (no rank), hard close, drain, contiguity, final, merit, precompute, publish; Redis result equals the DB result |
| Integration | `…/test_consumer_apply.py` | Duplicate messages; out-of-order seqs (latest keeps the highest); `max_acked_seq` monotonic; delete only after commit (simulate a crash between commit and delete: redelivery is a no-op) |
| Integration | `…/test_contiguity.py` | An injected missing batch seq blocks publication and opens an incident. A lost **final** batch is detected through the exam-Redis ack, the submit marker's or the client's `acked_through` (not only consumer-written values). An aggregate mismatch with `exam:sent` blocks. Ledger loss runs on fallback evidence and writes an incident note. A non-empty DLQ blocks. |
| Integration | `…/test_registration_reservation.py` | Paid reservation → capture → confirmed; lapse → released and counter decremented; capture after lapse → auto-refund enqueued |
| Integration | `…/test_void_exam.py` | Void from `live` and from `published`: merit unpublished, notifications and refunds enqueued, audited |
| Integration | `…/test_takeover.py` | Second device takes over: epoch increments; old token rejected at ingest; the acknowledged-answers endpoint restores |
| Integration | `…/test_extend_time.py` | Extension reaches the next ack and the status poll; the late rule uses the new `ends_at`; a per-attempt 15-min extension is not cut off by hard close (close_base follows it); `result_publish_at` moves |
| Integration | `…/test_invalidate_and_rescore.py` | Invalidate gives a new config and rescore; a published snapshot stays until approval; the republished snapshot has a new version |
| Integration | `…/test_non_live.py` | Mock auto-generated; answers via API; submit gives a result in under 5 s (timing assertion on a 100-question attempt, local); re-attempt is never ranked |
| Integration | `tests/modules/gam/integration/test_exam_xp.py` | +30 once per live attempt even with a duplicate event; the streak day counted on the Dhaka submission date; `exam.submitted` emitted at the submit marker or provisional close, so a blocked contiguity check does not delay XP or the streak; mock first attempt per day only |
| Integration | `tests/modules/exam/integration/test_lock_registry.py` | Missing `exam_lock` key with a running registration still locks; both Postgres and Redis down → fail closed for last-known registrants |
| Integration | `tests/modules/prac/integration/test_exam_copies.py` | Copies are idempotent; notebook includes exam mistakes; re-attempts update mastery |
| API | `tests/modules/exam/api/test_learner_api.py`, `test_admin_api.py`, `test_ingest_api.py` | Schemas, status codes, every error code in §C.6 |
| Authorization | `tests/modules/exam/api/test_authz.py` | Not registered gives 403; another user's attempt gives 404; restricted audience hidden; control room needs `exam.control`; merit privacy (no phone or full name; opted-out masked) |
| DB | `tests/modules/exam/db/test_partitions_and_checks.py` | Partition routing by `exam_starts_on`; live-exam publish-time check; uq constraints; archive job drops only archived months |
| Concurrency | `tests/modules/exam/concurrency/test_registration_cap.py` | 200 parallel registrations against cap 100 give exactly 100 (conditional counter, no advisory lock); concurrent lapse and confirm keep the counter exact |
| Concurrency | `…/test_parallel_consumers.py` | 4 consumers on the same message set produce identical final state |
| Concurrency | `…/test_close_tick_single.py` | Two `close_tick` workers never run the same phase twice (uq `(exam_id, phase)`) |
| Failure | `…/test_sqs_failure.py` | Queue raises: ingest returns 503 and never acks; the client resend succeeds after recovery |
| Failure | `…/test_postgres_slow.py` | Consumer DB latency injected: ingest acks continue (no DB on the path); lag rises and drains |
| Regression | `…/test_v2_trace.py` | v2 §6.2 table steps 1–12 as assertions |
| Performance | `tests/load/ingest_benchmark.js` (k6, staging) | Single instance: max req/s at p99 ack < 500 ms; the result is recorded |
| Performance | `tests/load/exam_live.js` + `exam_fault_injection.js` (k6) + `exam_verify.py` (staging) | **The 20k fault-injection test** (v2 §6.4): synchronised starts (random phase proven: the max 1 s request burst ≤ 2 × mean), 1% batch drop, consumer killed mid-exam, SQS throttle, 10% reconnect storm, 2% late answers. **Pass:** every acknowledged answer scored; every injected gap detected; merit identical across 3 replays; provisional score p95 < 5 s; results reads at publish served from Redis with zero DB queries (pg_stat_statements delta) |

**Coverage.** 85% overall. **95%** on:
- `exam/internal/scoring/*`, `exam/internal/merit/*`
- `exam/ingest/*` (public subpackage), `exam/internal/consumers/*`, `exam/lock_registry.py`
- `exam/internal/services/registration.py`, `attempt_start.py`, `token_refresh.py`
- `core/security/exam_token.py`

---

## F. Completion

### F.1 Acceptance criteria

1. The full live flow test passes with the memory queue, and again against localstack SQS.
2. `exam-ingest` imports no Postgres modules (isolation test plus import-linter).
3. Acknowledgement is sent only after SQS confirms. Proof: a fault test where the SQS send raises must never yield an ack.
4. The contiguity check detects 100% of injected gaps in the integration test and in the 20k run.
5. The provisional score (no rank) is available within 5 s at p95 after early submit or exam end in the 20k run. Merit publishes no earlier than end + 15 min (DB check plus scheduler test).
6. Result reads at `result_publish_at` hit Redis only (measured).
7. The **20,000-candidate fault-injection rehearsal on staging passes**. The ingest per-instance throughput is measured and recorded in [`17`](17_scalability_and_performance.md).
8. The control room extends time; extensions reach clients in the next ack. Invalidation leads to a rescore and a new snapshot requiring approval.
9. Exam XP is +30 once per live attempt; streak days count on exam submission; XP never depends on score.
10. ANL-02 history shows score and rank trends.

### F.2 Deliverables

- Migrations `b05_01`–`b05_09`.
- The EXAM module.
- `exam-ingest` and `exam-consumers` entry points.
- The `edge/` Worker.
- Load and fault harness scripts.
- Dashboards and alerts as code.
- Runbooks (pre-scale, freeze, SQS failure, DLQ, gap).
- The `openapi.json` update.
- The rehearsal report (numbers, graphs, pass/fail per criterion).

### F.3 Definition of done

[`21_definition_of_done.md`](21_definition_of_done.md), plus:
- the edge project passes `npm run check` (eslint, tsc strict, vitest, and the ≤ 200-line check);
- the rehearsal report is attached to the PR.

### F.4 Manual verification checklist

- [ ] Create a blueprint for SSC 2028 Physics with CQ 4-of-7, short 5-of-7, MCQ 25 and practical sections (practical marked not auto-scored).
- [ ] Schedule a live exam 25 h ahead, freeze it, and confirm the bundle in R2 has no keys (decrypt it locally with the unwrapped key).
- [ ] Register two test users; start on device A; take over on device B; confirm device A's next batch gets 401.
- [ ] Kill the consumer mid-run; restart it; confirm the final state is unchanged.
- [ ] Extend time by 5 min from the control room; confirm `ends_at` in the next ack.
- [ ] Watch the close phases in the control room; confirm the merit list, then publish it.
- [ ] Invalidate a question after publish; confirm the new snapshot waits for approval.

### F.5 Exit criteria before the next build

- The 20k rehearsal has passed.
- D5 and the S12 option are recorded as decided, with evidence.
- The `live_exam_cap` stays at 20,000 in config until the 25k rehearsal (B6 hardening) passes.
- All B5 alerts are wired in staging.

---

## Proposed additions (accepted)

All items below were reviewed during integration and **accepted**. Redis keys are in [`01`](01_database_design.md) §3.17, columns and constraint values in 01 §3/§4, and error codes in [`14`](14_api_contracts.md) §1.5. Cross-module functions listed here are part of the owning module's public API (`__init__.py`).

| Kind | Item | Reason |
|---|---|---|
| Redis key | `exam:epoch:{attempt_id}`, int, exam end + 1 day; rebuilt from `exam_attempts.epoch` | Ingest epoch check without Postgres |
| Redis key | `exam:inflight:{attempt_id}`, NX PX 10 s; safe to lose | One batch in flight |
| Redis key | `exam:live:{exam_id}`, HyperLogLog; safe to lose | Control-room participant count |
| Redis key | `exam:paper:{exam_id}:{lang}`, set of question_version_ids, exam end + 1 day; rebuilt from `exam_paper_items` | Ingest validates ids without Postgres |
| Constraint values | None needed: `exam_live`, `exam_practice`, `exam_reattempt` ship in the B3 CHECK | Exam copies for mastery |
| Error codes | `too_early` (425), `entry_closed` (410), `session_taken_over` (401), `batch_in_flight` (409), `seq_gap` (409), `exam_full` (409), `solutions_locked` (403), `not_final` (409), `reauth_required` (401), `payment_required` (403) | Add to 14 §1.5 |
| HTTP status | 425 Too Early | Not in 14 §1.5 |
| Function contract | `exam.scored_answers()` (read by the PRAC consumer), `exam.history_for()` (read by ANL), `tax.subtree_ids()`, `pay.has_entitlement(scope=exam)` | Cross-module public functions used here |

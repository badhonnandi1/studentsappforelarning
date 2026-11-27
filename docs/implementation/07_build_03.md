# Build 3 · Learning loop & gamification core

| Item | Value |
|---|---|
| Status | Planned · not started |
| Depends on | Build 2 merged, with exit criteria met ([06_build_02.md](06_build_02.md) §F.5) |
| Estimated effort | 11–15 backend person-weeks ([04 §6.3](04_backend_master_plan.md)) |
| Feature IDs | P0: PRAC-01, PRAC-02, PRAC-03, PRAC-04, PRAC-05, PRAC-06, PRAC-07, GAM-01, GAM-02, GAM-03, ANL-01, ANL-03, PAY-01, PAY-02, PLAN-01, PLAN-02, CMS-04a (practice part). Partial: NFR-09 (answer and session events, client telemetry), NFR-02 (practice gates), NFR-07 (leaderboard privacy), OFF-01 and OFF-02 (backend support). |
| Next build | [08_build_04.md](08_build_04.md) and [09_build_05.md](09_build_05.md), which can run in parallel |

---

## 0. How to run this build

**Read first:**
1. [`README.md`](README.md).
2. [`04_backend_master_plan.md`](04_backend_master_plan.md).
3. This document.
4. [`01_database_design.md`](01_database_design.md): §1.2, §3.4 (B3 rows), §3.8 (`corrections`), §3.9 (B3 rows), §3.11 (B3 rows), §3.13 (B3 rows), §3.14 (B3 rows), §3.17, and the whole of §5.
5. [`14_api_contracts.md`](14_api_contracts.md): the B3 rows.
6. [`system-design-v2.md`](../system-design-v2.md): §1 (learning session), §3.1–§3.6 (contracts) and §5 (gamification). These rules are the specification for the GAM engine.

**Preconditions:** Build 2 is on `main`. Staging has the pilot SSC 2028 Physics content published (at least one chapter of about 150 questions), or the dev seed bank (200 questions). `scripts/check.sh` is green.

**Branch:** `build/03-learning-loop`

**Commands:**
```bash
cd backend && uv sync && docker compose up -d
uv run alembic upgrade head
scripts/check.sh
uv run pytest -m "not load"
uv run pytest -m slow tests/regression/test_replay_million.py   # replay gate (C.13), run before merge
```

**Stop rule.** Stop when §F holds and the PR is open. Do not build the AI tutor (Build 4) or exams (Build 5). The exam XP (+30) and the exam streak day rule are added in Build 5, but their rule entries are defined here.

---

## A. Overview

| Item | Detail |
|---|---|
| Name | Learning loop & gamification core |
| Objective | A student can start any P0 practice session, answer online or offline with idempotent sync, and get Learn or Test feedback. They see the Mistake Notebook, progress, readiness and weak areas update. They earn XP within fair limits, keep a Dhaka-date streak with freezes, appear on leaderboards with privacy, and receive inbox and push notifications. Access is gated by entitlements and free quotas. Key corrections rescore practice answers. |
| Business value | This is the daily habit loop and the heart of the product (v2 §1). Gamification is first-class from the first recorded answer, and the event history that P1 adaptivity needs starts here (NFR-09). |
| Technical value | Proves the single answer transaction (v2 C8) under concurrency and replay, the hash-partitioned tables, the outbox-driven leaderboards and the rebuildability of every derived view. |
| Modules | PRAC (`practice`), GAM (`rewards` plus Redis), ANL (`analytics`), PAY (`commerce`: catalogue, entitlements, quotas), PLAN (`notify`: inbox, push, preferences), CMS (`corrections`, practice rescoring) |
| Dependencies | B1 (auth, outbox, jobs, idempotency, rate limits, SMS); B2 (published versions, scoring and comparators, TAX tree, error-report service, enrolments) |
| Complexity | 4/5 |
| Effort | 11–15 pw |

**Features**

| ID | Scope in this build |
|---|---|
| PRAC-01 | Custom builder: nodes, count, time limit, difficulty, source, type, negative marking |
| PRAC-02 | Learn mode (result, key and explanation immediately) and Test mode (receipt only; results at completion) |
| PRAC-03 | Chapter and topic practice; textbook-exercise mode (questions whose source is the textbook exercise) |
| PRAC-04 | Previous-year paper practice (paper pinned versions) |
| PRAC-05 | Mistake Notebook recomputed from rescored attempts; cleared after the 2 most recent rescored answers are correct |
| PRAC-06 | Bookmarks with folders; personal notes (keyed by question) |
| PRAC-07 | "Report error" from any question (creates a CMS error report) |
| GAM-01 | XP rules (v2 §5.1) with versioned config, a 300 XP daily cap from answers, the 24 h repeat rule, levels (50·n·(n−1)), and a daily goal (20, 50, 100 or 150; default 50; changes apply from the next Dhaka day) |
| GAM-02 | Streak on Dhaka dates by effective time; freezes (max 2, one per 7-day milestone); final settlement at 06:00 |
| GAM-03 | Leaderboards: weekly (Sat–Fri Dhaka), monthly, all-time × national, district, institution (self-reported), friends × track and exam year; top 100 plus own rank ± 5; mutual friend link by code or QR |
| ANL-01 | Dashboard: readiness per track, accuracy by subject, chapter and topic, attempts, study time, streak |
| ANL-03 | Weak areas: lowest-accuracy topics with ≥ 10 attempts; one tap starts a weak-topic session |
| PAY-01 | Catalogue: products, grants, validity in days or until the exam date |
| PAY-02 | Entitlement engine: union of active entitlements; free quotas (questions per day; AI messages and photo quotas are defined here and consumed in B4; live exams per week in B5); trials |
| PLAN-01 | Exam countdown per enrolled track |
| PLAN-02 | Notification inbox (the record), FCM push, categories, quiet hours for minors (22:00–07:00 Dhaka for non-critical), streak-at-risk reminder at the usual study hour |
| CMS-04a (practice) | Correction → `score_adjustments` in batches of 5,000 → notebook and progress recompute → +3 XP `key_correction` for newly correct answers → one notification per affected student |
| NFR-09 | `answer.recorded` and `session.completed` events through the outbox to S3; client telemetry `POST /v1/events:batch` through a Redis stream to S3 |
| OFF-01 / OFF-02 | Session payload ≤ 30 KB compressed for 10 questions in lite mode; `X-Lite-Mode`; minimum app version enforcement |

**Risks and blockers**

| Risk | Mitigation |
|---|---|
| Rule ambiguity (D6) | All numbers are in `reward_rules` v1, seeded from v2 §5 and changeable without code. The engine is driven by table-driven tests. |
| Answer-transaction latency under load | Budget below 25 ms of DB time p95. Per-user rows only. Version payloads cached. Measured in the B3 load test (§E). |
| Leaderboard correctness after Redis loss | Rebuild from the ledger by `recorded_at`; closed periods frozen in `leaderboard_snapshots` |
| 24 h repeat rule vs Dhaka-date rules | Resolved as a rolling 24 h window on `effective_at` ([00](00_architecture_review.md) correction 2) |
| FCM credentials | A fake push provider in dev and test; the real FCM HTTP v1 adapter behind settings |

---

## B. Database implementation

### B.1 Tables to create

| Schema | Tables | 01 ref |
|---|---|---|
| `practice` | `practice_sessions`, `session_items`, `attempt_answers` (P, HASH user_id × 64), `score_adjustments`, `mistake_entries`, `bookmark_folders`, `bookmarks`, `question_notes` | §3.9 |
| `analytics` | `topic_progress`, `daily_study`, `projection_versions`, `rebuild_audits` | §3.11 |
| `rewards` | `reward_rules`, `reward_transactions` (P, HASH user_id × 64), `user_totals`, `daily_activity`, `streak_state`, `streak_days`, `friend_codes`, `friend_links`, `board_flags`, `leaderboard_snapshots` | §3.13 |
| `commerce` | `products`, `product_grants`, `entitlements`, `entitlement_events`, `quota_policies` | §3.14 |
| `notify` | `notifications` (P, monthly), `deliveries` (P, monthly), `push_tokens`, `preferences` | §3.4 |
| `cms` | `corrections` | §3.8 |

There are no tables to modify. `identity.privacy_settings.leaderboard_visible` (B1) is read through `auth.get_board_visibility(user_ids)`.

### B.2 Relationships, indexes and constraints

**Practice**
- `practice_sessions.user_id` → `identity.users`; `track_enrolment_id` → `identity.track_enrolments`; `paper_id` → `qbank.papers`; `node_id` → `curriculum.taxonomy_nodes`.
- uq `(user_id, client_session_id)`; ix `(user_id, started_at DESC)`, `(user_id, status) WHERE status='open'`.
- `session_items` PK `(session_id, position)`; `question_version_id` → `qbank.question_versions`.

**`attempt_answers`**
- PK `(user_id, id)`. **No outgoing FKs** ([01 §1.1](01_database_design.md) exception, R-14: KEY SHARE and MultiXact contention on hot parent rows, and the option to move to a separate cluster). The answer service validates `question_version_id` through `qb.get_versions()`, takes the user and enrolment from the actor, and the nightly orphan check reports dangling ids.
- No FK from other schemas into it.
- Per-partition indexes: `(user_id, question_id, effective_at)` (notebook, 24 h rule), `(question_version_id)` (rescoring), `(user_id, session_id)`, `(user_id, effective_dhaka_date)` (daily counts in rebuilds).
- Checks: `context IN ('practice_learn','practice_test','written_self','exam_live','exam_practice','exam_reattempt','duel')`. This canonical list is created in B3 so B5 and B9 need no constraint swap. Also `effective_source IN ('device','receipt')`; `scoring_source IN ('auto','self','teacher','ai_estimate')`; `time_spent_ms BETWEEN 0 AND 86400000`.

**Other practice tables**
- `score_adjustments` uq `(user_id, answer_id, correction_id)`; ix `(correction_id)`.
- `mistake_entries` PK `(user_id, question_id)`; ix `(user_id, status, subject_node_id)`.
- `bookmarks` uq `(user_id, question_id, folder_id) NULLS NOT DISTINCT`; `folder_id` → `bookmark_folders` `ON DELETE CASCADE`.

**Analytics**
- `topic_progress` PK `(user_id, track_enrolment_id, node_id)`; ix `(user_id, track_enrolment_id, attempts)`.
- `daily_study` PK `(user_id, track_enrolment_id, dhaka_date)`.

**Rewards**
- `reward_transactions` PK `(user_id, id)`; uq `(user_id, idempotency_key)`; ix `(recorded_at)` and `(user_id, effective_dhaka_date)`. No outgoing FKs (same exception as `attempt_answers`). Idempotency keys are built only by `gam/contracts/reward_keys.py` (§C.6.1).
- Checks: `kind IN ('xp','freeze','badge','coins')`; `amount <> 0`; `reverses_id IS NULL OR amount < 0`.
- `daily_activity` PK `(user_id, dhaka_date)`; `CHECK (xp_from_answers >= 0)`. The cap value comes from the rule, so it is not a DB constant; `01 §3.13` shows 300 as the v1 rule.
- `streak_state` `CHECK (freezes_held BETWEEN 0 AND 2)`.
- `streak_days` PK `(user_id, dhaka_date)`, `status IN ('counted','frozen','missed')`.
- `friend_links` `CHECK (user_a_id < user_b_id)`.

**Commerce**
- `entitlements` ix `(user_id, status, ends_at)`; uq partial `(user_id, product_id) WHERE source='trial'`; `CHECK (ends_at IS NULL OR ends_at > starts_at)`.
- `quota_policies` uq `(plan_code, feature, effective_from)`.

**Notify**
- `notifications` PK `(id, created_on)`; ix `(user_id, created_at DESC)`; partial `(user_id) WHERE read_at IS NULL`.
- `push_tokens.token_hash` uq.

**CMS**
- `corrections` uq `(old_version_id, new_version_id)`; `rescoring_status IN ('pending','running','done','failed')`.

### B.3 Migration sequence

| Revision | Content |
|---|---|
| `b03_01_commerce_catalogue` | `products`, `product_grants`, `quota_policies`; seed a free plan, a paid plan and quotas (questions per day 50 free, unlimited paid; AI messages 10 and 100; photos 2 and 20; live exams per week 1 free) **[Rule v2 §4.6; to be revised under D2]** |
| `b03_02_commerce_entitlements` | `entitlements`, `entitlement_events` |
| `b03_03_practice_sessions` | `practice_sessions`, `session_items` |
| `b03_04_practice_attempts` | `attempt_answers` partitioned HASH (64 partitions, created by the helper) and its indexes; no outgoing FKs |
| `b03_05_practice_projections` | `score_adjustments`, `mistake_entries` |
| `b03_06_practice_personal` | `bookmark_folders`, `bookmarks`, `question_notes` |
| `b03_07_analytics` | `topic_progress`, `daily_study`, `projection_versions` (seed `mistakes v1`, `topic_progress v1`), `rebuild_audits` |
| `b03_08_rewards_ledger` | `reward_rules` (seed v1 from §C.6), `reward_transactions` partitioned HASH × 64, no outgoing FKs |
| `b03_09_rewards_state` | `user_totals`, `daily_activity`, `streak_state`, `streak_days` |
| `b03_10_rewards_social` | `friend_codes`, `friend_links`, `board_flags`, `leaderboard_snapshots` |
| `b03_11_notify_inbox` | `notifications`, `deliveries` (monthly partitions, 3 ahead), `push_tokens`, `preferences`; seed templates for streak, correction and generic categories |
| `b03_12_cms_corrections` | `corrections` |
| `b03_13_permissions_seed` | `gam.review`, `gam.rules`, `pay.catalogue`, `plan.templates` |

### B.4 Transaction requirements

The answer transaction follows [01 §5.1](01_database_design.md), and is specified step by step in §C.4. The other boundaries are:

| Operation | Boundary |
|---|---|
| Start session | One transaction: select versions through QB (read only), insert the session and items. Idempotent on `(user_id, client_session_id)`. The quota check and increment happen before the transaction (Redis), with a refund if the transaction fails. |
| Complete session | Lock the session row; compute the summary from its answers; set `completed`; reward `session_completed` (if ≥ 5 answers) inside a savepoint; outbox `session.completed` |
| Streak settlement (lazy in the answer transaction, plus the 06:00 job for inactive users) | Lock `streak_state` → write `streak_days` for each unsettled day before the answer's day, in date order → recompute the length per day (counted +1; frozen unchanged; missed reset to 0) → consume a freeze or reset → update state. One transaction per user (§C.6.4). |
| Rescoring batch (PRAC job `prac.rescore_correction`) | One transaction per 1,000 answers: `score_adjustments` insert `ON CONFLICT DO NOTHING` → recompute affected notebook and progress rows → reward `key_correction` through GAM → advance the cursor carried in the job payload → emit `rescoring.progress` (and `rescoring.completed` at the end), which CMS consumes to update `cms.corrections` |
| Entitlement grant or revoke | Entitlement row plus `entitlement_events` plus outbox `entitlement.changed` |
| Notification create | Insert the notification; enqueue a delivery job (in the consumer's transaction, with `processed_events`) |

### B.5 Data-integrity requirements

- `attempt_answers` rows are immutable once `is_correct` is set. The repository's only update is `set_self_mark(user_id, answer_id, …)`, which runs `UPDATE … WHERE is_correct IS NULL` for written self-marked answers (inserted with `is_correct` NULL) and fails if 0 rows change. Corrections are `score_adjustments` only.
- The ledger is append-only; reversals are new rows with `reverses_id`. B3 does not use reversals, because XP is kept on downward corrections (v2 §5.5).
- Every derived view can be rebuilt with the same functions the transaction uses (`analytics.rebuild_user`, `practice.rebuild_notebook`, `rewards.rebuild_totals`, `rewards.rebuild_board`). This is proven by the replay test and the weekly 1% audit job.
- A leaderboard API never returns a phone number, full name or photo. It returns only `first_name` and `institution_name` (self-reported label), and opted-out users are excluded (NFR-07).

---

## C. Backend implementation

### C.1 Implementation steps (exact order)

1. **PAY catalogue and entitlements** (`b03_01`–`02`):
   - `check_entitlement(user, scope)`: scopes are track, syllabus version, node with the `is_free` inheritance from TAX, exam, exam series, and feature;
   - grant and revoke functions (used by trials now, admin in B6, payments in B6);
   - the quota service (Redis counters and policies);
   - the catalogue and entitlement routes;
   - a cache of 30 s per user, invalidated on `entitlement.changed`.
2. **PRAC sessions** (`b03_03`):
   - the `NextQuestionPolicy` protocol and `RuleBasedPolicy`;
   - the session composers per kind (§C.5);
   - start, resume and abandon;
   - the payload builder (Learn vs Test, lite mode);
   - routes.
3. **PRAC attempts** (`b03_04`–`05`): the scoring call into `qb.score_response`; the effective-time function; the notebook recompute; the answer save service **without** the GAM call first. Tests R1 and R2 come first.
4. **ANL** (`b03_07`): `record_answer(session, …)` (topic_progress for the topic and all ancestors, daily_study); dashboard and readiness; weak areas; rebuild functions.
5. **GAM engine** (`b03_08`–`10`):
   - the rules loader (by effective date);
   - the pure reward calculator `compute_answer_rewards(ctx) -> list[RewardIntent]`;
   - the ledger writer;
   - the daily activity and cap;
   - levels;
   - the streak engine (counting, freezes, settlement);
   - the table-driven tests from v2 §5.5 **before** wiring into PRAC.
6. **Wire the answer transaction:** PRAC → ANL → savepoint(GAM) → outbox. Add the repair job `gam.repair_from_answer`. Batch sync endpoint.
7. **Session completion** with the summary and the session reward; the home endpoint ("tomorrow" card ranking: open mistakes in the subject → weakest topics → next path topic).
8. **Leaderboards:**
   - consumer `gam.board.apply` on `reward.granted`;
   - Redis sorted-set updates by period × track × audience;
   - the read API with neighbours and privacy;
   - the period rollover snapshot job;
   - the rebuild job.
   - Then friends (codes and links) and the anti-abuse flags review.
9. **PLAN inbox and push** (`b03_11`):
   - the notification service (`plan.notify(session, user_id, category, template, params, dedupe_key)`);
   - the delivery job with quiet hours;
   - the FCM adapter (HTTP v1, OAuth service account) and the fake;
   - push token routes;
   - preferences;
   - the usual study hour job (nightly mode of answer hours over 14 days);
   - the streak-at-risk scheduler (GAM decides, PLAN sends);
   - countdowns.
10. **PRAC personal:** bookmarks, folders, notes (`b03_06`); student error reports (`cms.create_error_report`).
11. **CMS-04a practice rescoring** (`b03_12`). The dependency direction (R-03) is that CMS never imports PRAC, ANL or GAM:
    - a CMS consumer of `question.corrected` with `key_changed` creates a `corrections` row and emits `correction.created` (outbox);
    - the PRAC job `prac.rescore_correction` (queue `rescoring`) consumes it. It iterates `attempt_answers` by `question_version_id` = old, per partition, with a cursor in the job payload, scoring with `qb.score_response(new_version_key)`;
    - PRAC writes `score_adjustments` and recomputes the notebook, calling `anl.apply_rescore` and `gam.record_correction_reward` (allowed PRAC → ANL and PRAC → GAM edges);
    - PRAC emits `rescoring.progress` every batch and `rescoring.completed` at the end. CMS consumes both to update `cms.corrections` (status, affected users);
    - PRAC asks PLAN to notify each affected user once, at the end;
    - admin resolve and correction-status routes stay in CMS.
12. **Telemetry:** `POST /v1/events:batch` → validation → `XADD telemetry:stream` → the `nfr.telemetry.flush` job (every 60 s) writes Parquet to S3. Practice events from the outbox already flow through the B1 relay.
13. **Rebuild and audit:**
    - `analytics.rebuild_audits` weekly job (1% sample: recompute in memory, compare with live, record mismatches, alert);
    - the replay test harness;
    - load test scenarios.
14. Authorization matrix, OpenAPI snapshot, build report.

### C.2 Folder structure changes

New:
- `modules/prac/internal/{models,repositories,services,schemas,routes,events,jobs,policies}`;
- `modules/gam/internal/{models,repositories,services,engine,boards,schemas,routes,jobs}`;
- `modules/anl/internal/...`;
- `modules/pay/internal/...`;
- `modules/plan/internal/{...,push}`;
- `cms/internal/rescoring/`;
- `tests/modules/{prac,gam,anl,pay,plan}/`;
- `tests/regression/`;
- `tests/load/`.

### C.3 Files to create

**PAY (`modules/pay/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `pay/__init__.py` | Public: `check_entitlement`, `get_access_summary`, `grant`, `revoke`, `consume_quota`, `refund_quota`, `quota_status`, `routers()` | 50 |
| `pay/contracts/access.py` | `AccessScope`, `AccessDecision{allowed, reason, plan_code}`, `QuotaFeature` enum, `QuotaStatus` | 80 |
| `pay/internal/models/catalogue.py` | `Product`, `ProductGrant`, `QuotaPolicy` | 90 |
| `pay/internal/models/entitlement.py` | `Entitlement`, `EntitlementEvent` | 70 |
| `pay/internal/repositories/catalogue.py` | Products by track; grants by product | 70 |
| `pay/internal/repositories/entitlements.py` | Active for user (at a time), insert, update status and ends, events | 100 |
| `pay/internal/services/access.py` | `check_entitlement`: free node (`is_free` on the node or an ancestor, via TAX) OR an active entitlement whose grant covers the scope (track ⊇ syllabus version ⊇ node by ancestry; exam; feature); per-user cache 30 s | 150 |
| `pay/internal/services/grants.py` | `grant(session, user, product, source, source_ref, starts, ends)`, `revoke`, `shorten`; validity "until exam date" via `tax.get_exam_date`; events and outbox `entitlement.changed` | 140 |
| `pay/internal/services/quotas.py` | Plan code = paid if any active entitlement grants the feature; `consume_quota` = Lua `INCR` with a limit check and the period TTL (Dhaka day or week); `refund_quota`; Redis loss → recount from Postgres (`attempt_answers` today) | 140 |
| `pay/internal/services/trials.py` | Start a trial once per product (partial unique) | 60 |
| `pay/internal/routes/catalogue.py` | `/v1/products`, `/v1/me/entitlements`, `/v1/me/trials` | 90 |
| `pay/internal/routes/admin_catalogue.py` | Admin products and quota policies | 110 |
| `pay/internal/schemas/*.py` (`catalogue.py`, `admin.py`) | Schemas | 2 × 90 |

**PRAC (`modules/prac/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `prac/__init__.py` | Public: `get_answer_context(user, answer_id)` (used by AI in B4), `record_external_attempts` (B5), `routers()`, `job_handlers()`. Rescoring is a PRAC job triggered by an event, so no rescoring function is exported to CMS (R-03). | 50 |
| `prac/contracts/answers.py` | `SaveAnswerRequest` (v2 §3.2: `answer_id`, `question_version_id`, `lang`, `response`, `time_spent_ms`, `answered_at`, `client{monotonic_since_sync_ms, last_server_sync}`), `AnswerResult`, `AnswerContextDTO` | 110 |
| `prac/contracts/events.py` | `AnswerRecorded`, `SessionCompleted` payload models | 60 |
| `prac/internal/models/session.py` | `PracticeSession`, `SessionItem` | 90 |
| `prac/internal/models/attempt.py` | `AttemptAnswer`, `ScoreAdjustment` | 90 |
| `prac/internal/models/personal.py` | `MistakeEntry`, `BookmarkFolder`, `Bookmark`, `QuestionNote` | 100 |
| `prac/internal/repositories/sessions.py` | Insert with conflict, get with items, lock, list | 110 |
| `prac/internal/repositories/attempts.py` | `insert_answer` (`ON CONFLICT DO NOTHING RETURNING`), get by `(user, id)`, answers for a question ordered by `effective_at`, recent attempt within 24 h, by session, by version (cursor scan per partition) | 150 |
| `prac/internal/repositories/adjustments.py` | Insert, effective correctness for answers (latest adjustment wins) | 70 |
| `prac/internal/repositories/mistakes.py` | Ensure row, lock, update, list open | 80 |
| `prac/internal/repositories/personal.py` | Bookmarks, folders, notes | 110 |
| `prac/internal/policies/base.py` | `NextQuestionPolicy` protocol: `select(ctx, candidates, n) -> list[version_id]` | 40 |
| `prac/internal/policies/rule_based.py` | P0 policy: unseen first (no attempt by the user), then by author difficulty rising, then by oldest attempt; at most one per family when `family_id` is set | 110 |
| `prac/internal/services/candidates.py` | Build the candidate set from filters via `qb.get_selectable_versions` (nodes with descendants, type, difficulty, source, tenant, lang) and entitlement filtering | 130 |
| `prac/internal/services/compose_lesson.py` | Lesson rule (v2 §1.1): 1 recall + 2–3 application + 1 past-paper + 1 open mistake in this subject; size 5–8; concept card id from the topic's concept note | 130 |
| `prac/internal/services/compose_other.py` | Custom, chapter, textbook (`source.kind = textbook_exercise`), past paper (paper items in order), mistakes, weak topic, similar (explicit ids from AI in B4) | 150 |
| `prac/internal/services/session_start.py` | Validate enrolment; quota (`questions_per_day` counted at answer time, not start; start only checks access); compose; persist; payload | 140 |
| `prac/internal/services/payload.py` | Build `QuestionPayload` per item (no key in Test mode; lite mode media refs; signed media URLs); payload size guard | 120 |
| `prac/internal/services/effective_time.py` | Effective time = `last_server_sync + monotonic_since_sync_ms` when inside the window (6 h P0, configurable to 72 h) and `answered_at` agrees within 2 min; else `received_at`; returns `(effective_at, source)` | 80 |
| `prac/internal/services/answer_save.py` | The answer transaction (§C.4) orchestration | 170 |
| `prac/internal/services/answer_validate.py` | Session state (open), item belongs to the session, language matches, response type matches, time limit, `answered_at` not in the future by > 5 min | 110 |
| `prac/internal/services/notebook.py` | `recompute_entry(session, user, question_id)`: lock row, read the ordered answers with adjustments, apply the rule (wrong or skipped adds; the two most recent correct clear); returns the transition (added, cleared, unchanged) | 120 |
| `prac/internal/services/answer_sync.py` | Batch sync (≤ 50): each answer in its own transaction, in `answered_at` order; per-item results | 90 |
| `prac/internal/services/session_complete.py` | Summary (score, correct, wrong, skipped, XP earned in session, streak, next suggestion); Test-mode results revealed | 130 |
| `prac/internal/services/self_mark.py` | Written answers (`context = written_self`), inserted with `is_correct` NULL, are self-marked once against the rubric (`UPDATE … WHERE is_correct IS NULL`; `scoring_source=self`; attempt XP only) | 90 |
| `prac/internal/services/home.py` | Path of topics (TAX order for the enrolment), "tomorrow" card, review-mistakes count, countdown, banners (B6 adds banners) | 140 |
| `prac/internal/services/adjustments.py` | `apply_adjustments(session, batch)` used by `prac.rescore_correction`: insert adjustments, recompute notebook entries, call ANL recompute, return newly-correct answers | 120 |
| `prac/internal/services/personal.py` | Bookmarks, folders, notes; error-report hand-off to CMS | 110 |
| `prac/internal/routes/sessions.py` | Start, get, complete, abandon | 110 |
| `prac/internal/routes/answers.py` | Save, sync, self-mark | 90 |
| `prac/internal/routes/personal.py` | Mistakes, bookmarks, folders, notes, error reports | 140 |
| `prac/internal/routes/home.py` | `/v1/home`, `/v1/papers`, `/v1/papers/{id}`, `/v1/concept-notes/{id}` (reads through QB) | 90 |
| `prac/internal/schemas/*.py` (`sessions.py`, `answers.py`, `personal.py`, `home.py`) | Schemas | 4 × 110 |
| `prac/internal/jobs/rebuild.py` | `prac.rebuild_notebook(user)` | 60 |

**ANL (`modules/anl/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `anl/__init__.py` | Public: `record_answer(session, …)`, `recompute_for_answers(session, …)`, `rebuild_user`, `routers()` | 40 |
| `anl/internal/models/progress.py` | `TopicProgress`, `DailyStudy`, `ProjectionVersion`, `RebuildAudit` | 90 |
| `anl/internal/repositories/progress.py` | Upsert increments (`ON CONFLICT DO UPDATE SET attempts = attempts + 1 …`) for the node list; reads by user and enrolment | 110 |
| `anl/internal/services/record.py` | Map version → primary node → ancestors (TAX); upsert topic, chapter, subject and paper levels; daily study | 100 |
| `anl/internal/services/dashboard.py` | Accuracy tree; attempts; study time (last 7 and 30 days); streak (via GAM); readiness | 140 |
| `anl/internal/services/readiness.py` | **[Rule]** coverage × recent accuracy weighted by chapter marks share. Weights come from `taxonomy_nodes.marks_weight` until EXAM blueprints exist (B5 swaps in the blueprint shares via `exam.get_chapter_weights`, falling back to node weights). Recent accuracy = the last 30 days or the last 50 answers per chapter. | 120 |
| `anl/internal/services/weak_areas.py` | Lowest accuracy topics with ≥ 10 attempts, top N (default 5) | 70 |
| `anl/internal/services/rebuild.py` | Recompute from attempts and adjustments (same functions), under `projection_version`; compare mode for audits | 140 |
| `anl/internal/jobs/audit.py` | Weekly 1% sample audit; mismatches recorded; event `anl.rebuild_mismatch` | 90 |
| `anl/internal/routes/progress.py` | Dashboard, weak areas | 70 |
| `anl/internal/schemas/progress.py` | Schemas | 90 |

**GAM (`modules/gam/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `gam/__init__.py` | Public: `record_answer_rewards(session, ctx) -> RewardOutcome`, `record_session_completed`, `record_correction_reward`, `record_exam_submitted` (B5), `get_summary`, `get_streak`, `routers()`, `job_handlers()` | 60 |
| `gam/contracts/rewards.py` | `AnswerRewardContext` (user, enrolment, answer_id, question_id, version, is_correct, previous transition of the notebook, time_spent_ms, time_estimate_s, effective_at, effective_dhaka_date, recorded_at, context, scoring_source, is_ai_item), `RewardOutcome` (xp_awarded, flags, streak, goal_reached) | 110 |
| `gam/internal/models/ledger.py` | `RewardRule`, `RewardTransaction` | 80 |
| `gam/internal/models/state.py` | `UserTotals`, `DailyActivity`, `StreakState`, `StreakDay` | 110 |
| `gam/internal/models/social.py` | `FriendCode`, `FriendLink`, `BoardFlag`, `LeaderboardSnapshot` | 80 |
| `gam/internal/engine/rules.py` | Typed `RuleSet` (pydantic) parsed from `reward_rules.rules`; `rules_for(date)` with a process cache | 120 |
| `gam/internal/engine/answer_rules.py` | Pure function: intents for attempted (+2 unless an XP-earning attempt within 24 h), correct (+3), mistake cleared (+5 once per question), with the rapid-guess flag (time < max(3 s, 15% × estimate) → flag, XP still awarded); self-marked → attempt XP only; AI items → none here | 140 |
| `gam/internal/engine/levels.py` | `level_for(xp) = max n : 50·n·(n−1) ≤ xp`; progress to next | 40 |
| `gam/internal/engine/streak_rules.py` | Day counts if ≥ 5 answers or ≥ 1 exam on the effective Dhaka date; milestones every 7 days grant a freeze (max 2); settlement decision per missed day | 100 |
| `gam/internal/repositories/ledger.py` | Insert transactions (`ON CONFLICT (user_id, idempotency_key) DO NOTHING RETURNING`); sums; by recorded window (rebuild); history page | 120 |
| `gam/internal/repositories/state.py` | Daily-activity insert-if-missing then `SELECT … FOR UPDATE` (cap computed in the service, §C.6.2); totals upsert; streak lock and update | 150 |
| `gam/contracts/reward_keys.py` | The only builder of reward idempotency keys (§C.6.1); public | 80 |
| `gam/internal/services/answer_rewards.py` | Orchestrates: rules → intents → cap → ledger → totals and level → daily activity (answers_count, goal reached → +10 `daily_goal`) → streak counting → outbox `reward.granted` per transaction | 170 |
| `gam/internal/services/session_rewards.py` | +10 `session_completed` (≥ 5 answers); `key_correction` +3; `exam_submitted` (B5 wiring) | 90 |
| `gam/internal/services/daily_goal.py` | Change goal (pending from the next Dhaka day) | 50 |
| `gam/internal/services/settlement.py` | `settle_through(session, user_id, before_date)`: the one settlement function, used lazily in the answer path and by the 06:00 job for inactive users (§C.6.4) | 130 |
| `gam/internal/services/summary.py` | Summary and history | 80 |
| `gam/internal/services/repair.py` | `gam.repair_from_answer`: reload the answer via PRAC's public `get_answer_context`, rerun `record_answer_rewards` (idempotent keys) | 70 |
| `gam/internal/boards/keys.py` | Board key builder: `lb:{period}:{period_key}:{track_key}:{audience}:{audience_id}`; period keys from `recorded_at` (week starts Saturday 00:00 Dhaka; month; all) | 70 |
| `gam/internal/boards/apply.py` | Batched consumer of `reward.granted` (kind xp): for every applicable board (national, district, institution; friends computed at read; 9–12 boards per reward), call the Lua script in `boards/apply.lua` with the entries in ledger order; skip if hidden (`board_flags`) | 110 |
| `gam/internal/boards/apply.lua` | Per board: read `lb:marker:{board}` (last applied `(recorded_at, id)`); skip entries at or below it; `ZINCRBY` the rest and advance the marker in the same script (atomic). A retry after a crash re-applies nothing. | 40 |
| `gam/internal/boards/read.py` | Top 100 (`ZREVRANGE`), own rank (`ZREVRANK`) ± 5; friends board = `ZMSCORE` over the friend set for the period; hydrate names via `auth.get_board_profiles(ids)` (first name and institution only; opted-out filtered) | 140 |
| `gam/internal/boards/rollover.py` | At period close + 5 min: snapshot the top 100 into `leaderboard_snapshots`; set TTLs | 90 |
| `gam/internal/boards/rebuild.py` | Rebuild a board from the ledger by `recorded_at` window, per hash partition, streaming; atomic swap via a temp key and `RENAME` | 120 |
| `gam/internal/services/friends.py` | Friend code issue and rotate; add by code (mutual, `user_a < user_b`), remove; max 200 friends | 100 |
| `gam/internal/services/flags.py` | Board flags: increment on rapid-guess events (from the answer flags); auto-hide after N flags in 7 days **[Rule: 20]**; review decisions (audited) | 100 |
| `gam/internal/services/reminders.py` | Daily scheduler: users with an active streak and no counted activity today → schedule `plan.notify` at the usual study hour (dedupe per user per day) | 90 |
| `gam/internal/routes/rewards.py` | Summary, daily goal, history, leaderboards | 110 |
| `gam/internal/routes/friends.py` | Friends routes | 70 |
| `gam/internal/routes/admin.py` | Flags, rules, rebuild | 100 |
| `gam/internal/schemas/*.py` (`rewards.py`, `boards.py`, `admin.py`) | Schemas | 3 × 90 |
| `gam/internal/jobs/schedule.py` | Registers settlement (06:00 Dhaka daily, fan-out by user batches), rollover, reminders | 80 |

**PLAN additions (`modules/plan/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `plan/__init__.py` (modify) | Add `notify(session, user_id, category, template_code, params, dedupe_key, critical=False)`, `schedule_notify(…, at)`, `get_usual_study_hour` | 50 |
| `plan/internal/models/inbox.py` | `Notification`, `Delivery`, `PushToken`, `Preference` | 110 |
| `plan/internal/repositories/inbox.py` | Insert, list page, mark read, unread count | 90 |
| `plan/internal/repositories/push.py` | Tokens upsert and invalidate; deliveries | 80 |
| `plan/internal/services/notify.py` | Render a template (bn/en by user locale), create the inbox row, enqueue delivery; dedupe via `processed_events` keyed on the dedupe key | 120 |
| `plan/internal/services/quiet_hours.py` | Minors: non-critical pushes between 22:00 and 07:00 are delayed to 07:00; adult quiet hours from preferences | 70 |
| `plan/internal/push/base.py`, `fake.py`, `fcm.py` | `PushProvider` protocol; fake; FCM HTTP v1 (service account JWT, `messages:send`, `UNREGISTERED` → invalidate token), circuit breaker | 30 + 40 + 130 |
| `plan/internal/jobs/deliver.py` | `plan.push.deliver` job | 90 |
| `plan/internal/jobs/study_hour.py` | Nightly usual-study-hour computation (mode of the hour over 14 days, via ANL `daily_study`, or the PRAC public function `answer_hours(user)`) | 70 |
| `plan/internal/services/countdowns.py` | Per enrolled track via `tax.get_exam_date` | 50 |
| `plan/internal/routes/inbox.py` | Notifications, mark-read, push tokens, preferences, countdowns | 130 |
| `plan/internal/routes/admin_templates.py` | Templates | 60 |
| `plan/internal/schemas/inbox.py` | Schemas | 100 |

**CMS additions**

| Path | Responsibility | ~Lines |
|---|---|---|
| `cms/internal/models/correction.py` | `Correction` | 50 |
| `cms/internal/rescoring/consumer.py` | Consumer of `question.corrected` (when `key_changed`): create the correction (dedupe) and emit `correction.created` | 70 |
| `cms/internal/rescoring/progress.py` | Consumer of `rescoring.progress` and `rescoring.completed`: update `cms.corrections` | 60 |
| `prac/internal/jobs/rescore_correction.py` | `prac.rescore_correction`: iterate partitions × cursor; per batch of 1,000 compute new correctness via `qb.score_response(new_version_key)`; write adjustments; call ANL and GAM (`gam.record_correction_reward` for newly correct); emit progress; at the end emit `rescoring.completed` and notify affected users (one per user) through PLAN | 160 |
| `cms/internal/services/resolve.py` | Resolve an error report: if the key changes, require a new verified version (link); otherwise close with a resolution | 100 |
| `cms/internal/routes/admin_corrections.py` | `:resolve`, `GET corrections/{id}` | 80 |

**NFR additions**

| Path | Responsibility | ~Lines |
|---|---|---|
| `nfr/internal/routes/events.py` | `POST /v1/events:batch` | 70 |
| `nfr/internal/services/telemetry.py` | Validate events (allow-listed types: `screen_view`, `lesson_open`, `question_view`, `time_on_question`, `client_timing`; ≤ 100 per batch; ≤ 64 KB), enrich with user and device, `XADD` | 100 |
| `nfr/internal/jobs/telemetry_flush.py` | Read the stream by consumer group, write Parquet, `XACK`; trim | 110 |
| `core/lite_mode.py` | Dependency reading `X-Lite-Mode` or `?lite=1` | 30 |

### C.4 The answer transaction (PRAC-02, v2 C8, 01 §5.1)

```
POST /v1/practice/sessions/{sid}/answers   body = SaveAnswerRequest, header Idempotency-Key = answer_id
pre-tx:
  a. rate limit T-answer; actor
  b. quota: consume_quota(user, questions_per_day)  (refund if step 1 returns duplicate or the tx fails)
tx (READ COMMITTED, statement_timeout 2s):
  1. INSERT attempt_answers … ON CONFLICT (user_id,id) DO NOTHING RETURNING *
     → no row: SELECT stored row; return stored result with duplicate=true (no further writes)
  2. validate (session open & owned, item in session, response type)  [cheap checks happen before step 1 too]
  3. score = qb.score_response(version, response)  (cached version with key)
     effective_at, source = effective_time(...); effective_dhaka_date
     (fields are computed before the INSERT in step 1; listed here for clarity)
  4. notebook: transition = prac.notebook.recompute_entry(user, question_id)      [lock (user,question)]
  5. anl.record_answer(session, …)   → topic_progress (topic+ancestors), daily_study
  6. SAVEPOINT gam
       outcome = gam.record_answer_rewards(session, ctx(transition, …))
     on exception: ROLLBACK TO SAVEPOINT; enqueue gam.repair_from_answer(answer_id); outcome = pending
  7. nfr.publish(session, answer.recorded envelope)
  8. COMMIT
response:
  Learn: {answer_id, duplicate:false, is_correct, answer_key, explanation_html, effective_at, xp_awarded, reward_pending, streak, goal}
  Test:  {answer_id, duplicate:false}
```

- The same `answer_id` from another user is a distinct row under `(user_id, id)`. No other user's data is ever returned ([00](00_architecture_review.md) correction 1).
- A replay with a different body but the same `answer_id` returns the stored row (`duplicate: true`) and logs `answer_replay_mismatch`. The stored row is the truth.
- Learn mode reveals the key only for questions in the caller's own open or completed session.

### C.5 Session kinds and composition

| `kind` | Inputs | Composition |
|---|---|---|
| `lesson` | `node_id` (topic) | v2 §1.1 rule; mode learn; 5–8 items |
| `custom` | `filters{node_ids, count 5–100, time_limit_s?, difficulty[], source{kind, board, year, unit, exam_name}, types[], negative_marking}` | Policy over candidates |
| `chapter` | `node_id` (chapter or topic), count | Policy |
| `textbook` | `node_id` | Candidates with `source.kind = textbook_exercise`, in textbook order |
| `past_paper` | `paper_id` | Paper items in order; mode test by default |
| `mistakes` | `subject_node_id?`, count | Open notebook entries (oldest first); current published version of each question |
| `weak_topic` | `node_id` from weak areas | Policy restricted to the node |
| `similar` | `question_ids` (B4 photo solve) | Given ids, filtered by access |

Every session checks access: an entitlement for each item's node (free nodes always allowed). Items without access are dropped. If fewer than the minimum remain, the API returns 403 `forbidden` with `details.upgrade = product_ids`.

### C.6 GAM rules (seeded `reward_rules` v1, all **[Rule]** from v2 §5)

```json
{
  "xp": {"answer_attempted": 2, "answer_correct": 3, "mistake_cleared": 5, "session_completed": 10,
         "session_min_answers": 5, "daily_goal": 10, "mock_submitted": 20, "live_exam_submitted": 30,
         "key_correction": 3},
  "limits": {"answer_xp_daily_cap": 300, "repeat_window_hours": 24},
  "rapid_guess": {"fraction_of_estimate": 0.15, "min_seconds": 3},
  "daily_goal_options": [20, 50, 100, 150], "daily_goal_default": 50,
  "streak": {"min_answers": 5, "min_exams": 1, "freeze_every_days": 7, "max_freezes": 2,
             "settle_hour_dhaka": 6, "effective_window_hours": 6},
  "levels": {"formula": "50*n*(n-1)"},
  "boards": {"week_start": "saturday", "top_n": 100, "neighbours": 5, "auto_hide_flags_7d": 20}
}
```

**C.6.1 Idempotency keys (R-05).** Every key is built by **one public module**, `app/modules/gam/contracts/reward_keys.py` (about 80 lines). No other code builds a key string. The canonical formats, all scoped by `user_id` through the unique index:

| Function | Key |
|---|---|
| `answer_attempted(answer_id)` | `xp:answer_attempted:{answer_id}` |
| `answer_correct(answer_id)` | `xp:answer_correct:{answer_id}` |
| `key_correction(answer_id, correction_id)` | `xp:key_correction:{answer_id}:{correction_id}` |
| `mistake_cleared(question_id)` | `xp:mistake_cleared:{question_id}` |
| `session_completed(session_id)` | `xp:session_completed:{session_id}` |
| `daily_goal(dhaka_date)` | `xp:daily_goal:{dhaka_date}` |
| `mock_submitted(paper_or_exam_id, dhaka_date)` | `xp:mock_submitted:{paper_or_exam_id}:{dhaka_date}` |
| `live_exam_submitted(attempt_id)` | `xp:live_exam_submitted:{attempt_id}` |
| `written_attempt(submission_id)` | `xp:written_attempt:{submission_id}` (B6) |
| `ai_quiz_completed(session_id)` | `xp:ai_quiz_completed:{session_id}` (B7) |
| `freeze_grant(streak_started_on, milestone)` | `freeze:grant:{streak_started_on}:{milestone}` |
| `freeze_consume(dhaka_date)` | `freeze:consume:{dhaka_date}` |
| `badge(badge_code)` | `badge:{badge_code}` (B7) |
| `coins_*` | `coins:…` (B9) |

Tests:
- `tests/modules/gam/unit/test_reward_keys.py` holds golden values for every function.
- `tests/contract/test_reward_key_paths.py` drives one answer through the answer transaction, through `gam.repair_from_answer`, through `rewards.rebuild_totals`, and (from B5) through the exam consumer. It asserts that all four produce identical key sets.

**C.6.2 Cap (R-19: PostgreSQL has no `RETURNING` of old values):**
1. The answer XP intents (attempted, correct, cleared) are summed to X.
2. `INSERT INTO daily_activity … ON CONFLICT (user_id, dhaka_date) DO NOTHING`, then `SELECT xp_from_answers, rule_version FROM daily_activity WHERE … FOR UPDATE`.
3. Compute in the service: A = `max(0, min(X, cap − xp_from_answers))`.
4. `UPDATE daily_activity SET xp_from_answers = xp_from_answers + A …`.
5. A is split across the intents in order (attempted, correct, cleared), and only the non-zero intents are written.
6. Session, goal and exam XP are not capped.

The row lock serialises one user's concurrent answers only; there is no global hot row.

**C.6.3 Daily goal:**
- After the ledger write, `daily_activity.xp_total += awarded`.
- If `xp_total ≥ goal_xp` and `goal_reached_at IS NULL`, set `goal_reached_at` and write the `reward_keys.daily_goal(date)` row.
- The goal uses the effective Dhaka date (v2 §5.1).
- A pending goal change applies from `pending_goal_from`.

**C.6.4 Streak (R-06): settle lazily, then count.**

1. **Lazy settlement first.** Inside the GAM savepoint, before counting an answer for its effective Dhaka date D, the service locks `streak_state` (`FOR UPDATE`). It then settles every unsettled day d with `last_settled_date < d < D`, in date order, using the settlement rule below. So an answer at 00:30 that follows a missed day settles that day with the freeze the user still holds, before today is counted. Settling never touches D itself.
2. **Count D.** When D's `answers_count` reaches 5 (or `exams_submitted` reaches 1) and `D > last_settled_date`, set `streak_days(D) = counted`.
3. **Settlement rule**, applied per day in order, and the only place the length changes:
   - counted → `current_length += 1`;
   - frozen (a freeze was available and is consumed) → length unchanged;
   - missed (no freeze) → `current_length = 0`;
   - a counted day after a reset therefore becomes 1.
   The length for D is applied when D itself is settled. The summary shows `current_length` plus one if D is already counted ("today counts").
4. **Freezes.** When a settled length reaches a multiple of 7, grant a freeze with `LEAST(2, …)`, written as a ledger row keyed `reward_keys.freeze_grant(streak_started_on, milestone)`. The ledger is the only record of freeze grants and consumption.
5. **The 06:00 Dhaka job** (`gam.streak.settle`) only handles users who had **no activity** since their last settlement, that is with `last_settled_date < yesterday`. It applies the same rule up to yesterday. Active users have already been settled lazily.

**Tolerance window and final settlement:**
- **P0 (B3–B6).** The effective-time window is 6 h, so settlement at 06:00 next day is **final**. Answers that sync later for a settled day still earn XP but never change that day (C12).
- **From B7 (OFF-03).** A user with an active offline pack gets a **provisional** settlement at 06:00 and a **final** settlement when the 72 h window closes. A late valid answer inside the window can turn a provisional `missed` or `frozen` day into `counted`. A freeze consumed for that day is returned by a reversing ledger row (`reverses_id`). This is supervisor decision **S-9**.

**C.6.5 Leaderboard periods:**
- Each XP transaction counts toward the period containing its `recorded_at`, and the board for the track of its `track_enrolment_id`.
- Audiences: national; district (profile district); institution (profile institution, labelled self-reported); friends (computed).
- All-time boards exist per track.

### C.7 Jobs and workers

| Job kind | Queue | Trigger | Idempotency |
|---|---|---|---|
Queues are only the canonical list in `core/jobs/queues.py` (01 §4.1, R-04).

| Job kind | Queue | Trigger | Idempotency |
|---|---|---|---|
| `gam.repair_from_answer` | `gam` | Savepoint failure | Ledger keys (same `reward_keys` functions) |
| `gam.board.apply` | `gam` | Batched consumer of `reward.granted` (≤ 500 events per job) | `processed_events (consumer, relay_batch_id)` plus the per-board Lua marker (§C.8) |
| `gam.board.rollover` | `gam` | Saturday 00:05 and the 1st 00:05 Dhaka | `dedupe_key` period |
| `gam.board.rebuild` | `gam` | Admin, or after a Redis loss (readiness detects an empty marker key) | Temp key swap |
| `gam.streak.settle` | `gam` | 06:00 Dhaka, users with no activity since the last settlement only; fan-out by user id range (1,000 per job) | Per-user lock and state; `dedupe_key = settle:{range}:{date}` |
| `gam.reminders.schedule` | `gam` | Hourly; schedules for users whose study hour is next | `dedupe_key = remind:{user}:{date}` kept until `dedupe_until` = end of that Dhaka day |
| `plan.push.deliver` | `notify` | Notification created | `processed_events` |
| `plan.study_hour.compute` | `notify` | Nightly 03:00 | Pure upsert |
| `prac.rescore_correction` | `rescoring` (throttled: 1 worker) | Consumer of `correction.created` (emitted by CMS) | Cursor in the payload plus unique adjustments |
| `cms.rescoring.progress` | `default` | Consumer of `rescoring.progress` and `rescoring.completed` (emitted by PRAC) | Updates `cms.corrections` status and counts; idempotent by status |
| `anl.audit.sample` | `maintenance` | Weekly | Recorded run |
| `nfr.telemetry.flush` | `maintenance` | Every 60 s | Consumer group acks |
| `pay.entitlements.expire` | `maintenance` | Every 10 min: mark ended entitlements expired, with an event | Status transition |

### C.8 Caching (Redis)

| Key | Notes |
|---|---|
| `quota:{user}:{feature}:{period}` | 01 §3.17 |
| `lb:*` | 01 §3.17 |
| `gam:usual_hour:{user}` | 01 §3.17 |
| `telemetry:stream` | 01 §3.17 |
| `qv:*` | B2 |
| `pay:access:{user}` | 30 s; invalidated on `entitlement.changed`. **Proposed addition.** |
| `lb:marker:{board}` | Last applied ledger position `(recorded_at, id)` for that board, read and advanced atomically by `apply.lua` together with `ZINCRBY` (R-16). Missing → rebuild. |
| `prac:session:{session_id}` | Payload cache for resume, 2 h. **Proposed addition.** |

### C.9 Events

| Event | Producer | Consumers |
|---|---|---|
| `answer.recorded` (v2 §3.3) | PRAC | S3 log; PLAN study hour (via log); B7 consumers |
| `session.completed` | PRAC | S3 log |
| `reward.granted` | GAM | Boards; S3 log |
| `streak.settled` | GAM | S3 log |
| `entitlement.changed` | PAY | Cache invalidation |
| `notification.created` | PLAN | Delivery |
| `correction.created` | CMS | PRAC `prac.rescore_correction` |
| `rescoring.progress`, `rescoring.completed` | PRAC | CMS (updates `cms.corrections`); S3 log |

### C.10 Error handling

| Code | When |
|---|---|
| 409 `conflict` | A session is not open |
| 404 | An item is not in the session (never 403, to avoid leaking existence) |
| 429 `quota_exhausted` | `details{feature, limit, resets_at}` |
| 403 `forbidden` | `details.upgrade` |
| 422 `validation_error` | Response type mismatch |

The GAM failure path returns 200 with `reward_pending: true`; it is never a 500.

### C.11 Security requirements

- Ownership checks on every session, answer, bookmark, note and notification route (BOLA tests).
- Keys appear only in Learn-mode responses and after completion in Test mode.
- **T-content** limit: distinct questions per user per hour, counted at session start and resume (NFR-06a groundwork; crawl detection in B6).
- Leaderboards expose only `first_name`, `institution_name`, rank, XP and `is_self`. Minors are treated the same (NFR-07, C13). Opted-out users are excluded from others' views but see their own rank.
- Telemetry is sanitised: no free text over 200 characters, and no PII fields.

### C.12 Configuration

`EFFECTIVE_WINDOW_HOURS` (6), `ANSWER_TX_STATEMENT_TIMEOUT_MS` (2,000), `SESSION_MAX_ITEMS` (100), `SYNC_BATCH_MAX` (50), `FCM_PROJECT_ID`, `FCM_CREDENTIALS` (secret), `PUSH_BACKEND` (fake, fcm), `TELEMETRY_STREAM_MAXLEN`, `RESCORE_BATCH_SIZE` (1,000), `ENTITLEMENT_CACHE_TTL_S` (30).

### C.13 The replay harness (release gate in v2 §8.2)

`tests/regression/test_replay_million.py` (marker `slow`, about 20–40 min on CI large runners, run nightly and before merge):
1. Generate 1,000 users × 1,000 answers.
2. Add 5% duplicates and random reordering within a 6 h window, and across midnight and the Saturday boundary.
3. Play the stream through the service layer with a frozen, advancing clock.
4. Then rebuild every projection from scratch, and assert that the notebook, topic_progress, totals, daily activity, streak state and boards are identical to the live state.
5. Assert that no XP was granted twice: `count(distinct idempotency_key) = count(*)`.
6. A smaller version (20,000 answers) runs in the normal CI suite.

---

## D. API contracts

Common: Auth **User** unless stated; payloads follow [14 §2](14_api_contracts.md).

### D.1 Practice

**`GET /v1/home`** (T-read)
- `?enrolment_id=`
- Response: `{enrolment, path: [{node_id, name, state: done|current|locked|free, progress_pct}], tomorrow: {kind: review_mistakes|weak_topic|next_topic, node_id?, count}, mistakes_open: int, countdown: {exam_name, days}, rewards: SummarySmall, banners: []}`

**`POST /v1/practice/sessions`** (T-write; idempotency via `client_session_id`)
- Request: `{client_session_id: uuid, enrolment_id: uuid, kind: lesson|custom|chapter|textbook|past_paper|mistakes|weak_topic|similar, mode: learn|test, node_id?, paper_id?, filters?: CustomFilters, question_ids?: [uuid ≤ 20], lite?: bool}`
- `CustomFilters`: `{node_ids: [1–50], count: 5–100, time_limit_s?: 60–14400, difficulty?: [1–5], source?: {kind, board?, year?, unit?, exam_name?}, types?: [...], negative_marking?: {enabled, per_wrong: 0.25|0.5}}`
- Response 201: `{session_id, mode, kind, items: [QuestionPayload], time_limit_s?, concept_card?: {note_id, title}, started_at}`
- Errors: 404 node or paper; 403 `forbidden` (no access, `details.upgrade`); 422 (too few candidates: `details.available`); 409 (the enrolment is not active).
- Replays with the same `client_session_id` return the same session.

**`GET /v1/practice/sessions/{id}`** (Owner, T-content) → the session with items and the answers so far (Learn: results; Test: receipts only).

**`POST /v1/practice/sessions/{id}/answers`** (Owner, T-answer; idempotency via `answer_id`)
- Request: `SaveAnswerRequest`. Constraints:
  - `response` must match the item type (`{selected: [label]}`, `{value: number}`, `{text: str ≤ 5000}`, `{pairs: {...}}`, `{bool}`, `{blanks: [...]}`);
  - `time_spent_ms` from 0 to 86,400,000;
  - `answered_at` not more than 5 minutes in the future;
  - `client.monotonic_since_sync_ms ≥ 0`.
- Response 200: `AnswerResult`.
- Errors: 404 (item not in the session); 409 (session not open); 422; 429 `quota_exhausted`.

**`POST /v1/practice/answers:sync`** (T-answer)
- Request: `{answers: [SaveAnswerRequest & {session_id}] (1–50)}`
- Response 200: `{results: [{answer_id, status: stored|duplicate|rejected, error?: {code}, result?: AnswerResult}]}`
- Each answer is processed independently.

**`POST /v1/practice/sessions/{id}:complete`** (Owner, R) → `{score, correct, wrong, skipped, marks?, negative_loss?, xp_earned, streak: {length, counted_today}, goal: {xp, target, reached}, next: {kind, node_id}, results?: [AnswerResult] (Test mode)}`. Errors: 409 (already completed returns the stored summary with 200).

**`POST /v1/practice/sessions/{id}:abandon`** → 204.

**`POST /v1/practice/answers/{answer_id}/self-mark`** (Owner, R)
- Request: `{parts: [{subpart_id, marks_awarded ≥ 0 ≤ subpart.marks, rubric_point_ids: []}]}`
- Response 200: `{marks_awarded, scoring_source: "self"}`
- Errors: 409 (already self-marked); 422 (marks out of range).

**`GET /v1/practice/mistakes`** → `?subject_node_id=&cursor=` → `Page<{question_id, subject, first_wrong_at, last_answer_at, consecutive_correct}>` plus `{counts_by_subject}`

**`GET /v1/practice/bookmark-folders`**; **`POST`** `{name (1–40)}` → 201; **`PATCH /{id}`** `{name?, sort?}`; **`DELETE /{id}`** → 204, which cascades bookmarks in the folder (the question bookmark without a folder remains if it exists).

**`PUT /v1/practice/bookmarks/{question_id}`** `{folder_id?}` → 200; **`DELETE`** `?folder_id=` → 204; **`GET /v1/practice/bookmarks`** `?folder_id=&cursor=` → `Page<{question_id, folder_id, created_at, snippet}>`

**`PUT /v1/practice/notes/{question_id}`** `{body: str (1–2000)}` → 200; **`DELETE`** → 204.

**`POST /v1/questions/{question_id}/error-reports`** (T-write, O)
- Request: `{question_version_id, kind: wrong_key|typo|wrong_explanation|out_of_syllabus|other, text?: str ≤ 500}`
- Response 201: `{report_id, status}`
- Limit: 20 per user per day (429). Text moderated (422 `moderation_blocked`).

**`GET /v1/papers`** → `?board=&year=&unit=&track_id=&cursor=` → `Page<{paper_id, title, board, year, unit, total_marks, duration_min, question_count}>`
**`GET /v1/papers/{id}`** → detail without questions. Questions arrive only through a `past_paper` session.

**`GET /v1/concept-notes/{id}`** (T-content) → `{id, title, html, node_id}`. 403 without access to the node.

### D.2 Analytics

**`GET /v1/progress/dashboard`** → `?enrolment_id=` → `{readiness: {score 0–100, coverage, recent_accuracy, method_version}, tree: [{node_id, level, name, attempts, accuracy, children: [...]} up to topic], totals: {attempts, correct, study_time_ms_7d, study_time_ms_30d}, streak: {length, longest, freezes}}`

**`GET /v1/progress/weak-areas`** → `?enrolment_id=&limit=1..20` → `{items: [{node_id, name, accuracy, attempts, start_session: {kind: weak_topic, node_id}}]}`

### D.3 Gamification

**`GET /v1/rewards/summary`** → `{xp_total, level, xp_into_level, xp_for_next_level, today: {dhaka_date, xp, goal_xp, goal_reached, answers, capped: bool}, streak: {length, longest, freezes_held, today_counted, at_risk}, pending_goal?: {xp, from}}`

**`PUT /v1/rewards/daily-goal`** `{goal_xp: 20|50|100|150}` → 200 `{goal_xp_pending, effective_from}`. Errors: 422.

**`GET /v1/rewards/history`** → `?cursor=&kind=` → `Page<{id, kind, amount, reason_code, effective_dhaka_date, recorded_at}>`

**`GET /v1/leaderboards`**
- Query: `?period=weekly|monthly|all_time&track_id=&exam_year=&audience=national|district|institution|friends&period_key?` (a closed period → snapshot)
- Response: `{board: {period, period_key, audience, label: "self_reported"?, closes_at?}, top: [{rank, first_name, institution_name, xp, is_self}], me: {rank?, xp, neighbours: [...] (±5), visible: bool}}`
- Errors: 422 (an audience not available, e.g. district missing from the profile, returns 422 `profile_incomplete`).

**`GET /v1/friends`** → `{items: [{user_id, first_name, institution_name, since}]}`; **`GET /v1/friends/code`** → `{code (8 chars), qr_payload, rotated_at}`; **`POST /v1/friends`** `{code}` → 201 (409 already friends; 404 code; 422 self; 429 more than 20 per day); **`DELETE /v1/friends/{user_id}`** → 204.

**Admin (Staff):**
- `GET /v1/admin/gam/flags` (`gam.review`) → `Page<{user_id, flag_count, hidden, last_flag_at}>`.
- `POST /v1/admin/gam/flags/{user_id}:decide` `{hide: bool, reason}` (R, audited).
- `POST /v1/admin/gam/rules` (`gam.rules`, R) `{effective_from (≥ tomorrow, Dhaka), rules: RuleSet}` → 201 `{version}`. Validated by the RuleSet schema; audited.
- `POST /v1/admin/gam/boards:rebuild` `{period, period_key?, track_id?}` → 202 `{job_id}`.

### D.4 Commerce (catalogue and access)

**`GET /v1/products`** (Public) → `?track_id=` → `{items: [{id, code, kind, name, price: Money, validity: {kind, days?, until?}, grants_summary}]}`

**`GET /v1/me/entitlements`** → `{plan_code: free|paid, active: [{id, product, source, starts_at, ends_at}], quotas: [{feature, limit, used, resets_at}]}`

**`POST /v1/me/trials`** (R) `{product_id}` → 201 entitlement. Errors: 409 `conflict` (trial used); 422 (the product has no trial).

**`POST/PATCH /v1/admin/products[/{id}]`** (Staff:pay.catalogue, R)
- `{code, kind, name_bn, name_en, price_poisha ≥ 0, validity_kind, validity_days?, until_exam_track_id?, grants: [{scope_type, scope_id?, feature_code?, quota?}], trial_days?}`. Audited.

**`POST/PATCH /v1/admin/quota-policies[/{id}]`** `{plan_code, feature, limit_value ≥ 0, period: dhaka_day|dhaka_week, effective_from}`. Audited.

### D.5 Planner and notifications

**`GET /v1/countdowns`** → `{items: [{enrolment_id, track, exam_year, starts_on, days_left, is_confirmed}]}`

**`GET /v1/notifications`** → `?cursor=&unread_only=` → `Page<{id, category, title, body, deep_link, created_at, read_at}>` plus `{unread_count}`

**`POST /v1/notifications:mark-read`** `{ids?: [≤ 100], all?: bool}` → 204.

**`POST /v1/push-tokens`** `{token, platform: android|web, device_session_id}` → 201 (an existing token is reassigned to this user). **`DELETE /v1/push-tokens/{id}`** → 204.

**`GET/PUT /v1/notification-preferences`** `{push_enabled, quiet_start?: "22:00", quiet_end?: "07:00", categories: {streak, exam, results, content, payment: bool}}`. Minors cannot disable the enforced 22:00–07:00 hold. Payment and security categories are always on.

**`POST/PATCH /v1/admin/templates[/{code}]`** (Staff:plan.templates, R) `{code, lang, channel: push|sms|inbox, body (with {placeholders}), version}`. Audited.

### D.6 Corrections and telemetry

**`POST /v1/admin/error-reports/{id}:resolve`** (Role:content.triage, R) `{resolution: fixed_typo|key_corrected|explanation_fixed|not_an_error, new_question_version_id?, note}` → 200. A key correction requires a published new version that supersedes the reported one (else 422).

**`GET /v1/admin/corrections/{id}`** (Role:content.read) → `{status, old_version_id, new_version_id, processed, total_estimate, affected_users, started_at, finished_at}`

**`POST /v1/events:batch`** (User, T-write)
- Request: `{events: [{type, occurred_at, session_id?, question_version_id?, props: {...} ≤ 2 KB}] (1–100)}`
- Response 202: `{accepted: n, rejected: [{index, reason}]}`

---

## E. Testing strategy

| File | Type | Cases |
|---|---|---|
| `tests/modules/pay/test_access.py` | db | Free node and inherited free; track entitlement covers a node; expired does not; union of two entitlements; exam scope; cache invalidation on `entitlement.changed` |
| `tests/modules/pay/test_quotas.py` | integration | Daily reset at Dhaka midnight; paid plan limit; consume and refund; Redis flush → recount from Postgres |
| `tests/modules/prac/test_policy_rule_based.py` | unit | Unseen first; difficulty rising; family uniqueness |
| `tests/modules/prac/test_compose_lesson.py` | db | Composition counts (recall 1, application 2–3, past paper 1, mistake 1 when one exists); size 5–8; fallback when a category is empty |
| `tests/modules/prac/test_session_kinds.py` | api | Each kind creates the right items; past paper keeps order; access filtering and the 403 upgrade; `client_session_id` replay |
| `tests/modules/prac/test_payload.py` | unit | No key in Test mode or for unanswered questions; lite mode omits media bytes; 10-question lite payload ≤ 30 KB compressed (OFF-02 gate) |
| `tests/modules/prac/test_effective_time.py` | unit (table-driven) | Inside the window → device time; outside → receipt; skewed wall clock ignored; missing sync → receipt; future answers clamp; 72 h config |
| `tests/modules/prac/test_answer_save.py` | api | Learn returns key, explanation and XP; Test returns a receipt; duplicate returns stored with `duplicate: true`; the same id by another user → their own row and never A's data; replay with a different body returns the stored row |
| `tests/concurrency/test_answer_duplicate_race.py` | concurrency | 10 parallel posts of the same `answer_id` → 1 row, 1 set of rewards (R1) |
| `tests/concurrency/test_two_devices_same_question.py` | concurrency | Parallel answers to the same question from 2 devices → notebook consistent with the ordered recompute (R2) |
| `tests/concurrency/test_xp_cap_race.py` | concurrency | 50 parallel answers near the cap → total answer XP for the day = 300 exactly (R3); goal awarded once (R4) |
| `tests/modules/prac/test_notebook.py` | unit + db | Wrong adds; skipped adds; two most recent correct clear; out-of-order answers (effective_at) give the same state; adjustments rescore |
| `tests/modules/anl/test_record_and_dashboard.py` | db | Ancestor upserts; accuracy; study time by Dhaka date; readiness formula with node weights; weak areas threshold of 10 |
| `tests/modules/gam/test_answer_rules.py` | unit (table-driven) | Attempted +2; correct +3; the 24 h repeat rule (23:59 later → 0; 24:01 later → 2); cleared +5 once; rapid guess flagged but awarded; self-marked attempt only; AI items 0 |
| `tests/modules/gam/test_levels.py` | unit | 0→1, 100→2, 300→3, 1000→5, boundaries |
| `tests/modules/gam/test_v2_worked_example.py` | db | **v2 §5.5 exactly:** 23:58 offline answer, synced 00:05 twice, key corrected on 28 Nov → 1 attempt, 5 XP, streak 7 with 26 Nov counted; 2 XP in the week of Sat 21–Fri 27 Nov; +3 in the next week; notebook cleared |
| `tests/modules/gam/test_clock_cases.py` | db (20 table-driven cases) | Midnight crossing; Saturday rollover (Fri 23:58 answer recorded Sat 00:05 → board of the new week, streak and goal on Friday); month end; Dhaka vs UTC boundary (17:59Z/18:00Z); reboot (no monotonic → receipt time); device clock set back by 2 days; sync after 06:00 settlement (XP yes, day unchanged); exactly 6 h window edge; 5th answer arriving late; freeze consumed; two freezes max; milestone at 7 and 14 grants; streak reset with no freezes; daily goal change applies tomorrow; cap reached then session XP still awarded; duplicate with a different user id; key correction downward (XP kept); key correction upward (+3); rapid guess near 3 s minimum; web client with no monotonic clock |
| `tests/modules/gam/test_settlement.py` | db | Missed day with a freeze → frozen; without → reset to 0, and the next counted day → length 1; multi-day gap settled in date order; **lazy settlement:** a 00:30 answer after a missed day consumes the held freeze before counting today, so the streak survives; the 06:00 job skips users already settled lazily; idempotent rerun; concurrent late answer vs settlement (R5) |
| `tests/modules/gam/unit/test_reward_keys.py` | unit | Golden value for every `reward_keys` function (§C.6.1) |
| `tests/contract/test_reward_key_paths.py` | contract | One answer through the transaction, the repair job and `rebuild_totals` yields identical key sets; extended in B5 with the exam consumer |
| `tests/modules/gam/test_board_apply_lua.py` | integration | A batch applied twice → the score is counted once (marker); a crash after `ZINCRBY` of 3 of 9 boards → the retry completes the rest without double-counting |
| `tests/contract/test_job_queues.py` | contract | The `platform.jobs.queue` CHECK equals `core/jobs/queues.py`; every registered job kind uses a canonical queue |
| `tests/concurrency/test_settlement_vs_answer.py` | concurrency | Settlement and an answer for the same user at once → consistent state, day never changed after settled |
| `tests/modules/gam/test_boards.py` | integration | Weekly key by `recorded_at` Saturday start; national, district and institution apply; friends board computed; top 100 and neighbours; hidden users excluded; opted-out excluded for others but self sees rank; rollover snapshot is immutable; rebuild equals the incremental state |
| `tests/modules/gam/test_board_privacy.py` | authorization | Response contains only allowed fields; no phone, full name or photo; minors the same |
| `tests/modules/gam/test_friends.py` | api | Code add (mutual, ordered pair); self → 422; duplicate → 409; remove; rotation invalidates the old code |
| `tests/modules/gam/test_savepoint_failure.py` | db | Inject a GAM exception → the answer commits, `reward_pending: true`, repair job enqueued; running the repair awards exactly once |
| `tests/modules/plan/test_notify.py` | integration | Inbox row; push via fake; minor quiet hours delay to 07:00; adult preference respected; critical bypasses; FCM `UNREGISTERED` invalidates the token; dedupe |
| `tests/modules/plan/test_reminders.py` | db | Streak-at-risk scheduled once per day at the usual hour; none if already counted today |
| `tests/modules/prac/test_rescore_correction.py` | db | `correction.created` → PRAC job → adjustments for every answer on the old version across partitions; resumable after a kill mid-way (cursor); +3 XP only for newly correct, idempotent; notebook cleared; one notification per user; downward correction → mastery down, XP kept |
| `tests/modules/nfr/test_telemetry.py` | integration | Batch validation; Redis stream; flush to Parquet; rejected events reported |
| `tests/modules/test_authz_matrix_b3.py` | authorization | Every B3 route × {anon, owner, other user, staff with and without permission}; BOLA on session, answer, bookmark, note and notification ids |
| `tests/contract/test_events_b3.py` | contract | `answer.recorded`, `session.completed` and `reward.granted` validate against schema v1 and contain no PII |
| `tests/regression/test_replay_small.py` | regression | 20,000-answer replay (§C.13), in CI |
| `tests/regression/test_replay_million.py` | regression (slow) | The 1M replay gate |
| `tests/regression/test_previous_builds.py` | regression | B1 and B2 smoke flows |
| `tests/load/practice.js` (k6) | load | 1,000 concurrent simulated learners (Stage 1): session start + answers every 40 s + dashboard + leaderboard. Gates: answer save p95 < 150 ms, p99 < 400 ms; DB time per answer p95 < 25 ms; leaderboard read p95 < 50 ms; zero 5xx. Run on staging; results in the build report. |

---

## F. Build completion

### F.1 Acceptance criteria

1. Every B3 endpoint in [14](14_api_contracts.md) is implemented to the D-section contract, with API tests.
2. The v2 §5.5 scenario and the 20 clock and correction cases pass as automated tests.
3. The 20,000-answer replay passes in CI, and the 1M replay passes before merge: projections are identical and no idempotency key is duplicated.
4. The concurrency tests R1–R5 pass on real Postgres.
5. Lite payload for 10 questions is ≤ 30 KB compressed. Session start p95 ≤ 2.5 s under BD-3G is measured by a scripted client against staging (v2 §6.4 Gate 2), where client tooling allows; otherwise the server-side p95 is < 200 ms and the payload size gate applies.
6. The Stage 1 load test meets the gates in §E (answer p95 < 150 ms).
7. A practice correction rescores 100,000 synthetic answers in under 10 minutes without blocking the answer path (p95 of answer save during rescoring < 200 ms).
8. Leaderboards rebuilt after `FLUSHALL` equal the pre-flush state.
9. Coverage ≥ 85% overall; ≥ 95% on `prac/internal/services/answer_save.py`, `notebook.py`, `effective_time.py`, `prac/internal/jobs/rescore_correction.py`, `gam/internal/engine/*`, `gam/internal/services/answer_rewards.py`, `settlement.py`, `repair.py`, `gam/contracts/reward_keys.py`, `gam/internal/boards/apply.py`, `pay/internal/services/access.py`, `quotas.py`.
10. `scripts/check.sh` is green; no file over 200 lines.
11. **Stage-4 synthetic benchmark (R-12).** Run on a production-sized staging database: the same instance class as planned for Stage 3–4, the 64 partitions pre-filled with about 1B synthetic `attempt_answers` and matching ledger rows. Measure, at a target of **2,500 answer tx/s**:
    - the answer transaction (p95 and p99 DB time, lock waits, MultiXact usage);
    - outbox relay lag at about 2,500 events/s;
    - `processed_events` and total WAL rate against [`17`](17_scalability_and_performance.md) §2.2;
    - reward fan-out to 9–12 boards per reward through the Lua apply (Redis ops/s and lag p95 ≤ 5 s).

    The report records the **measured capacity** as evidence. It is not a pass or fail on 100k. If a measured value falls short of the 17 §2.2 planning figure, 01 §5 and 17 are revised before Build 4 starts (for example batch sizes, relay parallelism, instance class or partition placement).

### F.2 Deliverables

Code per §C.3; migrations `b03_01`–`b03_13`; the seeded rules v1 and the free/paid plans; the replay harness; the load scenario; the updated OpenAPI snapshot; and a build report with the load-test results.

### F.3 Definition of done

[`21_definition_of_done.md`](21_definition_of_done.md).

### F.4 Manual verification checklist (the v2 §8.1 week-6 slice, backend half)

- [ ] OTP sign-in → enrol in SSC 2028 → open a lesson on "নিউটনের গতিসূত্র" → answer wrong → see the key, the explanation and +2 XP.
- [ ] The question appears in the Mistake Notebook; the dashboard accuracy updates.
- [ ] Complete 5 answers → the streak day is counted; the summary shows XP and the streak.
- [ ] The weekly leaderboard shows the user with first name and institution (self-reported label).
- [ ] The next day, the streak-at-risk push is scheduled at the usual hour (fake push log).
- [ ] Correct a key in the CMS → the answer is rescored → +3 XP → the notification is in the inbox.

### F.5 Exit criteria before Builds 4 and 5

F.1 holds, including the benchmark report (item 11) and any revisions to 01 and 17 that it triggers. The PR is merged; staging is migrated and seeded; and the proposed additions are accepted or rejected in 01 and 14. Builds 4 and 5 may then start in parallel.

---

## Proposed additions (accepted)

All items below were reviewed during integration and **accepted**. Redis keys are in [`01`](01_database_design.md) §3.17, columns and constraint values in 01 §3/§4, and error codes in [`14`](14_api_contracts.md) §1.5. Cross-module functions listed here are part of the owning module's public API (`__init__.py`).

| Kind | Item | Reason |
|---|---|---|
| Redis key | `pay:access:{user}` (30 s) | Entitlement decision cache (01 §5.4 now specifies Redis, so invalidation works across processes) |
| Redis key | `lb:marker:{board}` | Per-board applied ledger position (R-16); its absence detects Redis loss so the board rebuild runs automatically |
| Redis key | `prac:session:{session_id}` (2 h) | Fast resume without re-reading versions |
| Function | `auth.get_board_profiles(user_ids)` returning `first_name`, `institution_name`, `visible` | Leaderboard hydration without GAM reading identity tables |
| Function | `exam.get_chapter_weights` (B5) used by ANL readiness | Swap from node weights to blueprint mark shares |
| Column | `practice.attempt_answers.track_enrolment_id NOT NULL` | Every attempt carries the enrolment (v2 §3.1); 01 lists it but not nullability |
| Note | Quota counting for `questions_per_day` happens at answer time, not session start | Matches PAY-02 wording ("questions/day"); stated here to avoid ambiguity |

# 11 · Build 7: P1 personalised learning and engagement

**Build:** 7 of 9 · **Priority band:** P1 · **Date:** 2026-11-27 · **Depends on:** Builds 1–6 merged and green · **Unblocks:** Build 8 (needs QB-10 families for EXAM-09), Build 9
**Read first:** [`04_backend_master_plan.md`](04_backend_master_plan.md), [`01_database_design.md`](01_database_design.md) §3.1–§3.13 and §5, [`14_api_contracts.md`](14_api_contracts.md) §1–§3, [`15_testing_and_quality_standards.md`](15_testing_and_quality_standards.md), [`21_definition_of_done.md`](21_definition_of_done.md)

---

## 0. How to run this build (coding-agent preamble)

1. Read the documents above. Of `01` you need the rows for `practice`, `analytics`, `qbank`, `curriculum`, `ai`, `rewards`, `cms`, `community`, `notify` and `identity.track_enrolments`. Of `14` you need every row with **B = 7**.
2. Confirm Build 6 is complete:
   - `git log --oneline -5` shows the Build 6 merge.
   - `scripts/check.sh` passes on `main`.
   - `alembic current` equals the head of `b06_*`.
3. Create the branch `build/07-learning-engagement`.
4. Implement section C in the stated order. Each step adds migrations, models, repositories, services, routes and jobs, with tests written alongside the code. Run `scripts/check.sh` after each step.
5. This build changes the learning loop behind stable APIs. **Every Build 3–6 test must keep passing unchanged.** If one needs to change, stop and write down why in the PR.
6. Statistics features read the **S3 Parquet event log through DuckDB jobs**, never by scanning `attempt_answers` in Postgres. The only OLTP reads allowed are per-user reads that use a primary-key prefix.
7. Verify section F and write the build report in the PR description. **Stop.** Do not start Build 8 and do not touch the frontend.

---

## A. Overview

| Item | Value |
|---|---|
| Name | P1 personalised learning and engagement |
| Objective | Turn the P0 loop into a personalised, sticky learning system, with every new behaviour derived from the attempt record and the event log already captured since Build 3 |
| Business value | Retention and differentiation: adaptive sets, reviews, mastery, coach, badges, leagues and community. These drive daily return and paid conversion. |
| Technical value | Proves that NFR-09 history supports adaptivity and analytics without new write paths on the answer transaction; establishes the DuckDB warehouse-job pattern |
| Complexity | 4 / 5: many features, few new correctness hazards; the risky ones are leagues rollover, badge idempotency, FSRS correctness and warehouse jobs |
| Effort | 14–20 backend person-weeks **[Assumption]** |
| Modules | PRAC, ANL, QB, TAX, AI, PLAN, GAM, CMS, COM, AUTH, PAY (read-only interfaces) |

### A.1 Features

| ID | Feature in this build |
|---|---|
| PRAC-08 | Adaptive practice. An Elo `NextQuestionPolicy` replaces the rule-based policy behind the same session API, aiming for 60–75% predicted success |
| PRAC-09 | Spaced repetition. FSRS `review_cards` for mistakes and flashcards, with a due-review queue |
| PRAC-10 | Daily Mix: one set per (user, enrolment, Dhaka date), made of 40% due reviews, 40% weak topics weighted by exam importance and 20% new path material |
| PRAC-11 | Speed drill. A session kind `speed_drill` with a per-question timer; its speed analytics feed ANL-05 |
| PRAC-12 | Onboarding diagnostic. A fixed-blueprint session that seeds `ability_estimates` and `mastery_state` |
| ANL-04 | Mastery map. Levels Not started, Learning, Proficient and Mastered per topic, shared across TAX-06 links |
| ANL-05 | Time analytics: time vs accuracy, rushed and slow patterns, guess detection, marks lost to negative marking |
| ANL-06 | Previous-year trend analytics (chapter frequency, most-asked, predicted important) from QB paper metadata and the event log |
| ANL-07 | Peer percentile within track, exam year and district |
| ANL-08 | Readiness forecast to the exam date, based on current pace |
| QB-10 | Question families and variants |
| QB-11 | Item statistics (p-value, discrimination, distractor %, average time) and an automatic "probably wrong key" flag raised to CMS |
| QB-12 | Concept notes, cheat sheets and formula sheets per topic, extending `concept_notes.kind` |
| QB-13 | Flashcard decks: editorial, auto-generated from facts, and user-made |
| QB-14 | Current-affairs feed: daily items, quizzes through the CMS workflow, a monthly compilation PDF |
| TAX-05 | Madrasah (Dakhil, Alim) and Technical (BTEB) trees. These are data imports through the existing tree importer, plus the `paper_tracks` sharing |
| TAX-06 | Cross-track topic links with weight; mastery shared across links |
| AI-06 | Socratic and direct tutor modes; a mode lock set by a guardian (lock storage arrives in B8) or a batch teacher |
| AI-08 | Quiz generator from a topic, notes or a photo. Items stay in `ai.ai_items`, labelled AI, and earn completion XP only |
| AI-09 | Chapter summariser (short notes, key points, formula list, mind map outline, last-night sheet). Reviewed once, then served to all |
| AI-10 | AI study coach: a weekly plan from exam date, mastery and available hours, written as `notify.study_plan_items` through PLAN; re-plans on missed days |
| AI-11 | Mistake diagnosis: clusters wrong answers into misconceptions and creates a targeted fix session |
| PLAN-03 | Study routine and calendar, written by the student or by AI-10, with reminders |
| GAM-04 | Badges through a configurable rules engine over events; awards are ledger rows of kind `badge` |
| GAM-05 | Weekly leagues: cohorts of 30, promotion and relegation at the Saturday 00:00 Dhaka rollover |
| GAM-06 | Challenges with a time window, goals over existing events and a reward transaction |
| GAM-07 | Share cards rendered on the server with a referral link; minors' cards show first name only |
| CMS-07 | AI-assisted authoring (draft explanations, variants, BN↔EN translation, auto-tags, likely-wrong key). Output lands as Draft and needs human approval |
| CMS-08 | Content coverage dashboard (questions per chapter, type and difficulty; gaps) |
| CMS-09 | Author productivity and payment tracking for freelancers |
| COM-01 | Per-question discussion threads: moderated, upvotes, verified-teacher answers pinned |
| COM-02 | Paid human doubt escalation: the tutor hands off to a mentor queue with an SLA |
| AUTH-06 | Track promotion flow with history preserved across tracks |
| OFF-03 | Backend for offline practice packs: encrypted chapter packs, expiry tied to the entitlement, the 72 h effective-time window, conflict handling |

**Total: 34 P1 IDs.**

### A.2 Dependencies

| Needs | From |
|---|---|
| `attempt_answers`, `mistake_entries`, the `NextQuestionPolicy` interface, session kinds | B3 |
| Event log in S3 Parquet (≥ 8 weeks of history for meaningful statistics) | B1 relay and B3 events |
| Reward ledger, rule versions, Redis weekly boards | B3 |
| AI provider layer, routing, canonical cache, eval harness, quotas, citations | B4 |
| Referral codes (share cards), entitlements, products | B3 and B6 |
| Teacher batches (teacher mode lock) | B6 |
| Moderation `moderate()` | B1 |

### A.3 Risks and blockers

| Risk | Mitigation |
|---|---|
| Too little history for item statistics and Elo calibration | Statistics jobs require minimum sample sizes (≥ 200 attempts per item for QB-11; ≥ 30 per topic per user for mastery), and show "insufficient data" below them |
| League rollover double-processing or a partial run | One job per week with a `dedupe_key` and a transactional cohort build. Outcomes are idempotent ledger keys. |
| Badge rules firing twice on replays | Each award is keyed `badge:{code}:{user_id}` (or `…:{period}` for repeatable badges) |
| AI summaries, quizzes and drafts leaking into the verified bank | Separate tables (`ai.ai_items`, `cms.ai_drafts`). Bank entry only through the CMS workflow (two-person verification). Import-boundary tests. |
| DuckDB jobs read data that is too large on one worker | Partition pruning by day and track. Pre-aggregated daily Parquet rollups written by the job. Worker memory cap with spill-to-disk. |
| AI-06 lock storage is in PAR (Build 8) | See §C.2 decision D7-1 |

---

## B. Database implementation

All tables come from [`01`](01_database_design.md) §3. Column definitions are in `01` §4. This build creates the tables below, changes existing constraints, and adds the items under "Proposed additions" (§G) once they are approved into `01`.

### B.1 Tables to create

| Schema.table | Feature | Notes |
|---|---|---|
| `practice.ability_estimates` | PRAC-08, PRAC-12 | PK `(user_id, node_id)`; updated in the answer transaction's GAM/ANL savepoint |
| `practice.review_cards` | PRAC-09 | ix `(user_id, due_at)`; partial uq `(user_id, card_type, question_id)` and `(user_id, card_type, flashcard_id)` |
| `practice.daily_mixes` | PRAC-10 | PK `(user_id, track_enrolment_id, dhaka_date)`; this is the uniqueness rule |
| `practice.diagnostic_blueprints` | PRAC-12 | One active per (track, syllabus version) |
| `analytics.mastery_state` | ANL-04 | PK `(user_id, node_id)` |
| `analytics.time_analytics` | ANL-05 | Written by the warehouse job |
| `analytics.trend_snapshots` | ANL-06 | Written by the warehouse job |
| `analytics.peer_percentiles` | ANL-07 | Written by the warehouse job |
| `analytics.readiness_forecasts` | ANL-08 | Nightly job |
| `qbank.question_families` | QB-10 | FK `questions.family_id → question_families.id` is added NOT VALID, then validated |
| `qbank.item_statistics` | QB-11 | PK `(question_version_id, window_code)` with window codes `all`, `90d` |
| `qbank.item_flags` | QB-11 | Raises a CMS error report through the CMS interface |
| `qbank.flashcard_decks`, `qbank.flashcards` | QB-13 | |
| `qbank.current_affairs_items`, `qbank.current_affairs_compilations` | QB-14 | |
| `curriculum.topic_links` | TAX-06 | `CHECK (node_a_id < node_b_id)` |
| `ai.ai_items`, `ai.ai_quizzes` | AI-08 | |
| `ai.chapter_summaries` | AI-09 | uq `(chapter_node_id, kind, lang)` |
| `ai.coach_plans` | AI-10 | |
| `ai.misconception_clusters` | AI-11 | |
| `notify.study_plan_items` | PLAN-03 | ix `(user_id, plan_date)` |
| `rewards.badge_definitions`, `rewards.user_badges` | GAM-04 | |
| `rewards.league_tiers`, `rewards.leagues`, `rewards.league_members` | GAM-05 | |
| `rewards.challenges`, `rewards.challenge_progress` | GAM-06 | |
| `rewards.share_cards` | GAM-07 | |
| `cms.ai_drafts`, `cms.author_tasks`, `cms.author_payouts` | CMS-07, CMS-09 | |
| `community.threads`, `community.posts`, `community.post_votes` | COM-01 | |
| `community.mentor_requests`, `community.mentor_replies` | COM-02 | |
| `practice.offline_packs` | OFF-03 | **Proposed addition** (§G.1) |

### B.2 Tables to modify (expand-only)

| Table | Change | Why |
|---|---|---|
| `qbank.concept_notes` | Widen `ck_concept_notes_kind` to add `cheat_sheet` and `formula_sheet` | QB-12 |
| `practice.practice_sessions` | None: all kinds including `review` and `ai_quiz` are in the B3 CHECK (01 §4.E G7-3). Verify only. | PRAC-09, AI-08 |
| `rewards.streak_days` | Add `is_provisional boolean NOT NULL DEFAULT false` (expand) | S-9 provisional settlement for offline-pack users (D7-8) |
| `ai.tutor_threads` | Use the existing `mode` and `mode_locked_by` columns; add `ck` values `direct` and `socratic` | AI-06 |
| `rewards.reward_transactions` | Widen the `kind` check to include `badge` if Build 3 shipped only `xp` and `freeze` | GAM-04 |
| `commerce.products` | Widen `ck_products_kind` to add `mentor_credits` | COM-02. **Proposed** (§G.4) |
| `institution.batches` | Add `tutor_mode_lock text NULL` | AI-06 teacher lock. **Proposed** (§G.2) |
| `identity.track_enrolments` | No change; `promoted_from_id` already exists | AUTH-06 |

### B.3 Migration sequence

Each file is ≤ 200 lines and has a reversible `downgrade` where possible. Constraint widenings are expand-only; there are no contract migrations in this build.

| # | Revision | Content |
|---|---|---|
| 1 | `b07_01_curriculum_topic_links` | `curriculum.topic_links` |
| 2 | `b07_02_qbank_families_notes` | `question_families`, the FK `NOT VALID` on `questions.family_id`, the `concept_notes.kind` widen |
| 3 | `b07_03_qbank_validate_family_fk` | `VALIDATE CONSTRAINT` (separate so it runs online) |
| 4 | `b07_04_qbank_stats_flags` | `item_statistics`, `item_flags` |
| 5 | `b07_05_qbank_flashcards_affairs` | Flashcard decks and cards; current affairs items and compilations |
| 6 | `b07_06_practice_adaptive` | `ability_estimates`, `review_cards`, `daily_mixes`, `diagnostic_blueprints`, the session kind widen |
| 7 | `b07_07_practice_offline_packs` | `offline_packs` (after §G.1 approval) |
| 8 | `b07_08_analytics_p1` | `mastery_state`, `time_analytics`, `trend_snapshots`, `peer_percentiles`, `readiness_forecasts` |
| 9 | `b07_09_ai_p1` | `ai_items`, `ai_quizzes`, `chapter_summaries`, `coach_plans`, `misconception_clusters`, the thread mode check |
| 10 | `b07_10_notify_study_plan` | `study_plan_items` |
| 11 | `b07_11_rewards_badges_leagues` | Badges, league tiers (seeded), leagues, members; `streak_days.is_provisional` (D7-8) |
| 12 | `b07_12_rewards_challenges_cards` | Challenges, progress, share cards, the ledger kind widen |
| 13 | `b07_13_cms_p1` | `ai_drafts`, `author_tasks`, `author_payouts` |
| 14 | `b07_14_community_threads` | Threads, posts, votes |
| 15 | `b07_15_community_mentors` | Mentor requests and replies, the product kind widen |
| 16 | `b07_16_inst_batch_mode_lock` | `institution.batches.tutor_mode_lock` (after §G.2 approval) |

### B.4 Transaction and integrity requirements

| Operation | Requirement |
|---|---|
| Answer save (existing B3 transaction) | Add to the savepoint, in this order: ability update for the answer's primary topic node (and linked nodes via TAX-06 at weight × K), review-card upsert for wrong answers, mastery-state recompute for that node. **No extra round trip on the success path:** use one `INSERT … ON CONFLICT DO UPDATE` per table. Budget: under 3 ms added DB time p95 **[Assumption]**. |
| Daily Mix creation | `INSERT … ON CONFLICT (user_id, track_enrolment_id, dhaka_date) DO NOTHING RETURNING`. On conflict, return the existing session. Composition and session creation happen in one transaction. |
| League rollover | One transaction per tier: freeze standings from Redis into `league_members.final_xp/final_rank/outcome`, then create the next week's leagues and members. Job `gam.league.rollover` with `dedupe_key = week_key`. Promotion and relegation rewards use keys `league:{week_key}:{user_id}`. |
| Badge award | Ledger insert with key `badge:{code}:{user_id}[:{period}]`, plus a `user_badges` insert, both in the consumer's job transaction with `processed_events` |
| Challenge completion | `challenge_progress` update with `completed_at IS NULL` guard, plus the reward ledger row (key `challenge:{id}:{user_id}`) |
| Mentor escalation | Entitlement debit (mentor credit: quota decrement through PAY), `mentor_requests` insert, outbox `mentor_request.created`, all in one transaction. Refunded as an entitlement credit if the SLA lapses with no answer. |
| Author payouts | `author_payouts` uq `(author_id, period)`; tasks are linked under row lock. Audited. |
| Promotion (AUTH-06) | Close the old enrolment (`status='completed'`), insert the new enrolment with `promoted_from_id`, and emit `enrolment.promoted`, in one transaction. History rows keep their old `track_enrolment_id`. |
| AI-generated content | Never written to `qbank.*` except by a reviewer's CMS action. A DB-role check in tests asserts the `ai-gateway` role has no `INSERT` on `qbank`. |

---

## C. Backend implementation

### C.1 Steps in dependency order

1. **TAX-05/06**: topic links (model, repo, service, admin routes, public read). Madrasah and BTEB tree seed files are imported through the B2 importer (`scripts/seed/tax05_*.json`, a data commit with no code change). `paper_tracks` rows link SSC and Dakhil shared papers.
2. **QB-10, QB-12**: families (admin CRUD; assigning `family_id` through the QB public function `assign_family`) and the concept-note kinds.
3. **Warehouse job framework (shared by QB-11 and ANL-05–08)**: `nfr/internal/warehouse/duckdb_runner.py` gives a read-only DuckDB connection over S3 Parquet with partition pruning, typed result rows and a memory cap. Each module owns its SQL file and job.
4. **QB-11**: nightly job `qb.item_stats.compute` writes `item_statistics`. Rows with a `probable_wrong_key` result upsert `item_flags`, which call `cms.open_error_report(kind='wrong_key', source='item_stats')`.
5. **PRAC-08, PRAC-12**: `EloPolicy` implements `NextQuestionPolicy`. It is selected per session by `runtime_config["prac.policy"]` (default `elo` once 30 attempts exist for the topic, otherwise `rule_based`). The ability update is a pure function in `practice/internal/services/elo.py`. Then come the diagnostic blueprint and the `kind=diagnostic` session start.
6. **PRAC-09**: FSRS as a pure module (`fsrs.py`, v4 parameters as config), a review-card writer in the answer transaction, the due queue, and `kind=review` sessions.
7. **ANL-04**: mastery levels from ability, accuracy and recency (pure `mastery_rules.py`), written in the answer savepoint and on promotion and diagnostic.
   - **Teacher-checked written marks (R-28):** an ANL consumer of `marking.teacher_checked` (emitted since B6) folds the marks into `mastery_state`.
   - A one-off backfill job replays the B6 events from the S3 log, idempotent through `processed_events`.
   - Self-marked and AI-estimate marks are never counted. TAX-06 propagation uses `curriculum.topic_links` through `tax.linked_nodes(node_id)`, which is cached.
8. **PRAC-10**: the Daily Mix composer (pure function over due reviews, weak topics and path) plus the create-once service.
9. **PRAC-11**: speed drill session kind, per-question timer in the session payload, `time_spent_ms` analytics.
10. **ANL-05–08**: warehouse jobs, read endpoints and caching (Redis, 1 h per user per metric).
11. **QB-13, QB-14**: decks and cards (editorial, user, auto-generated from facts via CMS-07 drafts) and the current-affairs feed. The monthly compilation PDF job reuses the B6 invoice PDF renderer with the Bangla font.
12. **AUTH-06**: the promotion service and endpoint.
13. **AI-06**: thread mode, a mode-lock resolver (decision D7-1) and a Socratic prompt version that passes the eval gate.
14. **AI-08, AI-09, AI-11**: generators on the B4 provider layer. Each route is registered in `ai.prompt_versions` with its own eval set and gate. Summaries use a review workflow through the CMS assignment queue (`kind='ai_review'`).
15. **PLAN-03 and AI-10**: study plan items CRUD, reminders through jobs, and the coach plan generator writing items through `plan.write_plan_items(session, items)`. Missed-day detection runs nightly and re-plans.
16. **GAM-04**: the badge rules engine (`badge_rules.py`, a declarative JSON evaluated against event payloads and counters) and a consumer per event type.
17. **GAM-05**: league assignment (Saturday 00:05 job), weekly Redis boards per league, rollover.
18. **GAM-06**: challenges (admin CRUD, join, a progress consumer, completion reward).
19. **GAM-07**: share-card renderer (Pillow + bundled Bangla font, server-side PNG to private S3, signed URL), referral code from PAY.
20. **CMS-07**: AI draft requests (job), decide endpoint. An accepted draft creates a CMS Draft version and never publishes.
21. **CMS-08, CMS-09**: the coverage report from `qb.coverage_counts()`, author tasks recorded from workflow events (consumer), and the payout run.
22. **COM-01**: threads and posts with `moderate()` on every post, votes, verified-teacher pin.
23. **COM-02**: mentor requests from a tutor message, the mentor queue with SLA, replies (text, image key, voice key), SLA breach job (credit refund and notify).
24. **OFF-03**: pack builder job (chapter → published versions with keys and explanations), AES-256-GCM pack encryption with a per-pack key wrapped per device session, expiry = min(entitlement end, 30 days), the pack download endpoint, and answer sync with the 72 h effective-time window.
    - **Accepted risk (R-30):** keys are on the device because Learn mode needs them, so a rooted phone can extract the chapter. Controls:
      - per-user watermarking (per-user item order plus an embedded user fingerprint);
      - per-user canary items mixed into every pack;
      - at most 5 packs per user per Dhaka day (429 `content_rate_limited`);
      - packs revoked and expired with the entitlement;
      - packs never contain exam papers or tenant-private content.

      Recorded in [`20`](20_risk_register.md) and [`18`](18_security_architecture.md) §11.

### C.2 Design decisions in this build

| # | Decision | Rationale |
|---|---|---|
| D7-1 | **AI-06 lock source.** The PAR module gets a public function `par.tutor_mode_lock(child_user_id) -> ModeLock | None` in this build. It returns `None` because no guardian link can exist before Build 8, where `parent.guardian_links` and `parent.parent_controls` are created and the function reads them. Teacher locks read `institution.batches.tutor_mode_lock` through `inst.tutor_mode_lock_for_student(user_id)`. The effective mode is the strictest lock, then the thread's own choice. | The B7 implementation is a correct, not placeholder, answer for the system state of B7. Creating `parent.*` tables early would ship half of PAR without link flows. B8 replaces only the function body, with no AI change. |
| D7-2 | Item statistics are computed only from the S3 log | Keeps scans of ~1B-row tables off OLTP (v2 §3.6) |
| D7-3 | Elo K-factor 24 for users with < 30 attempts in a topic and 12 after; item rating seeded from `difficulty_author` and replaced by QB-11 `p_value` once available | Standard Elo practice. Values are config (`runtime_config["prac.elo"]`), not code. |
| D7-4 | Mastery levels: Not started (0 attempts); Learning (< 60% recent accuracy or < 10 attempts); Proficient (≥ 60% over the last 20 with ability ≥ item median); Mastered (≥ 85% over the last 20, at least one correct after 7 days) **[Rule]** | Rebuildable from attempts; versioned via `projection_versions` |
| D7-5 | Linked-topic mastery propagates at `weight × 0.5` of the ability delta, never above the source level | Prevents a single strong topic inflating unrelated tracks |
| D7-6 | AI quiz items earn completion XP only (key `reward_keys.ai_quiz_completed(session_id)` = `xp:ai_quiz_completed:{session_id}`, +10 at ≥ 5 items) and never write `mistake_entries`, `ability_estimates` or `mastery_state`. Badges use `reward_keys.badge(code)` = `badge:{badge_code}`. No other key format is allowed (R-05). | v2 §4.9 |
| D7-8 | **Offline-pack streak settlement (S-9, R-06).** For users with an active offline pack, the 06:00 settlement is **provisional** (`streak_days.is_provisional = true`). Final settlement runs when the 72 h effective-time window for that day closes (`gam.streak.finalise`, hourly, queue `gam`, `dedupe_key = finalise:{user}:{date}`). A late valid answer inside the window turns a provisional `missed` or `frozen` day into `counted`, and a freeze consumed for it is returned by a reversing ledger row (`reverses_id` → the `freeze:consume:{date}` row). Users without a pack keep the P0 final settlement at 06:00. | Offline-pack users are the main offline audience. A final 06:00 settlement would cost them days they actually studied within the allowed window. |
| D7-7 | League cohorts: 30 per (track, tier, week), filled from the previous week's board order; top 5 promote, bottom 5 relegate **[Rule]**; minors displayed with first name and institution only | v2 §5.7, NFR-07 |

### C.3 Files to create or modify

Paths are relative to `backend/src/app/` unless they start with `tests/` or `migrations/`. Line counts are estimates; the hard limit is 200.

**Shared and platform**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/nfr/internal/warehouse/duckdb_runner.py` | Read-only DuckDB over S3 Parquet; partition pruning; memory cap; typed rows | 120 |
| `modules/nfr/internal/warehouse/parquet_paths.py` | Builds S3 paths by event type and date range | 60 |
| `modules/nfr/__init__.py` (modify) | Export `warehouse_query()` | +10 |
| `shared/fsrs.py` | FSRS v4 scheduler (pure) | 130 |
| `shared/elo.py` | Elo expected score and update (pure) | 60 |

**Curriculum (TAX)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/tax/internal/models/topic_links.py` | ORM | 35 |
| `modules/tax/internal/repositories/topic_links.py` | Create, delete, list linked nodes | 70 |
| `modules/tax/internal/services/topic_links.py` | Validation (different tracks, same level kind), cache invalidation | 90 |
| `modules/tax/internal/routes/topic_links.py` | Public read and admin write | 70 |
| `modules/tax/__init__.py` (modify) | `linked_nodes(node_id)` | +15 |
| `scripts/seed/tax05_madrasah.json`, `tax05_bteb.json` | Seed trees (data) | data |

**Question bank (QB)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/qb/internal/models/families.py` | ORM: families | 35 |
| `modules/qb/internal/models/statistics.py` | ORM: item statistics, item flags | 60 |
| `modules/qb/internal/models/flashcards.py` | ORM: decks, cards | 55 |
| `modules/qb/internal/models/current_affairs.py` | ORM: items, compilations | 50 |
| `modules/qb/internal/repositories/families.py` | CRUD, assign | 70 |
| `modules/qb/internal/repositories/statistics.py` | Upsert stats, flags; read by version | 80 |
| `modules/qb/internal/repositories/flashcards.py` | Deck and card CRUD; list by node | 100 |
| `modules/qb/internal/repositories/current_affairs.py` | Feed by date, compilations | 70 |
| `modules/qb/internal/services/families.py` | Family rules (same type, same primary node) | 80 |
| `modules/qb/internal/services/item_stats_job.py` | DuckDB job: p-value, point-biserial discrimination, distractor %, avg time, wrong-key heuristic | 150 |
| `modules/qb/internal/services/flashcards.py` | Editorial and user decks; ownership; moderation of user decks | 120 |
| `modules/qb/internal/services/current_affairs.py` | Feed, publish through workflow, monthly compilation enqueue | 110 |
| `modules/qb/internal/jobs/compilation_pdf.py` | Monthly compilation PDF | 90 |
| `modules/qb/internal/sql/item_stats.sql` | DuckDB SQL (not Python; still ≤ 200 lines) | 80 |
| `modules/qb/internal/routes/admin_families.py` | Admin families | 60 |
| `modules/qb/internal/routes/admin_flashcards.py` | Admin decks | 60 |
| `modules/qb/internal/routes/admin_current_affairs.py` | Admin current affairs | 60 |
| `modules/qb/internal/routes/flashcards.py` | Learner decks | 70 |
| `modules/qb/internal/routes/current_affairs.py` | Learner feed | 40 |
| `modules/qb/internal/routes/stats.py` | Staff item stats | 40 |
| `modules/qb/internal/schemas/p1.py` | Request and response models for the above | 150 |
| `modules/qb/__init__.py` (modify) | `assign_family`, `coverage_counts`, `family_of`, `item_rating` | +30 |

**Practice (PRAC)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/prac/internal/models/adaptive.py` | ORM: ability, review cards, daily mixes, diagnostic blueprints | 110 |
| `modules/prac/internal/models/offline_packs.py` | ORM (after §G.1) | 40 |
| `modules/prac/internal/repositories/abilities.py` | Upsert ability, read by user and node | 70 |
| `modules/prac/internal/repositories/review_cards.py` | Upsert, due query | 80 |
| `modules/prac/internal/repositories/daily_mixes.py` | Insert-or-get | 50 |
| `modules/prac/internal/services/policy_elo.py` | `EloPolicy` (selects items near the 60–75% target band) | 140 |
| `modules/prac/internal/services/policy_select.py` | Chooses the policy per session from config and history | 50 |
| `modules/prac/internal/services/answer_projections_p1.py` | Savepoint hooks: ability, review card, mastery call | 120 |
| `modules/prac/internal/services/reviews.py` | Due queue; review session start | 100 |
| `modules/prac/internal/services/daily_mix.py` | Composer (pure) plus create-once | 150 |
| `modules/prac/internal/services/diagnostic.py` | Start from blueprint; seed abilities on completion | 120 |
| `modules/prac/internal/services/speed_drill.py` | Session options and per-question timers | 60 |
| `modules/prac/internal/services/offline_packs.py` | Build, encrypt, expiry, revoke on entitlement change | 150 |
| `modules/prac/internal/services/offline_sync.py` | 72 h window rules; retired-version handling | 100 |
| `modules/prac/internal/jobs/offline_pack_build.py` | Pack build job | 80 |
| `modules/prac/internal/routes/adaptive.py` | `reviews/due`, `daily-mix`, `diagnostic`, `abilities` | 90 |
| `modules/prac/internal/routes/offline_packs.py` | Pack endpoints (after §G.1) | 60 |
| `modules/prac/internal/schemas/p1.py` | Schemas | 140 |

**Analytics (ANL)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/anl/internal/models/p1.py` | ORM: mastery, time analytics, trends, percentiles, forecasts | 110 |
| `modules/anl/internal/repositories/mastery.py` | Upsert and read map | 70 |
| `modules/anl/internal/repositories/warehouse_outputs.py` | Upsert job outputs; read per user | 90 |
| `modules/anl/internal/services/mastery_rules.py` | Pure level rules (D7-4, D7-5) | 110 |
| `modules/anl/internal/services/mastery.py` | Recompute for node and links; called in the savepoint | 100 |
| `modules/anl/internal/services/time_analytics_job.py` | DuckDB: time vs accuracy, rushed and slow, guesses, negative-mark loss | 130 |
| `modules/anl/internal/services/trends_job.py` | Chapter frequency over papers (QB interface) and log | 120 |
| `modules/anl/internal/services/percentiles_job.py` | Cohort percentile tables | 100 |
| `modules/anl/internal/services/forecast.py` | Pace model to exam date (linear on coverage × accuracy trend, with a confidence band) | 120 |
| `modules/anl/internal/sql/time_analytics.sql`, `trends.sql`, `percentiles.sql` | DuckDB SQL | 60–100 each |
| `modules/anl/internal/routes/p1.py` | `mastery`, `time-analytics`, `trends`, `percentile`, `forecast` | 110 |
| `modules/anl/internal/schemas/p1.py` | Schemas | 120 |
| `modules/anl/__init__.py` (modify) | `recompute_mastery(session, …)`, `mastery_for(user, nodes)` | +20 |

**AI**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/ai/internal/models/p1.py` | ORM: AI items, quizzes, summaries, coach plans, clusters | 130 |
| `modules/ai/internal/services/modes.py` | Mode resolution (thread choice vs locks D7-1) | 80 |
| `modules/ai/internal/services/quiz_generator.py` | Topic, notes or photo → items; label AI; session `kind=ai_quiz` | 150 |
| `modules/ai/internal/services/summaries.py` | Generate per chapter and kind; review state; serve published | 130 |
| `modules/ai/internal/services/coach.py` | Plan from exam date, mastery and hours; re-plan; write PLAN items | 150 |
| `modules/ai/internal/services/misconceptions.py` | Cluster wrong answers (distractor + topic + model label); fix session | 140 |
| `modules/ai/internal/jobs/coach_replan.py` | Nightly missed-day detection | 70 |
| `modules/ai/internal/jobs/misconception_scan.py` | Weekly per active user | 70 |
| `modules/ai/internal/prompts/socratic-v1.md`, `quiz-v1.md`, `summary-v1.md`, `coach-v1.md`, `misconception-v1.md` | Prompt files (versioned) | data |
| `modules/ai/internal/routes/p1.py` | Mode, quizzes, summaries, coach, misconceptions | 120 |
| `modules/ai/internal/routes/admin_summaries.py` | Review endpoint | 40 |
| `modules/ai/internal/schemas/p1.py` | Schemas | 130 |
| `tests/eval/sets/socratic_v1.yaml`, `quiz_v1.yaml`, `summary_v1.yaml`, `coach_v1.yaml` | Eval set pointers (items in S3) | data |

**Planner (PLAN)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/plan/internal/models/study_plan.py` | ORM | 40 |
| `modules/plan/internal/repositories/study_plan.py` | CRUD; range query | 80 |
| `modules/plan/internal/services/study_plan.py` | Student CRUD; ownership; reminder scheduling | 120 |
| `modules/plan/internal/jobs/plan_reminders.py` | Reminder send respecting quiet hours | 70 |
| `modules/plan/internal/routes/study_plan.py` | CRUD routes | 80 |
| `modules/plan/__init__.py` (modify) | `write_plan_items(session, items, source, coach_plan_id)` | +20 |

**Gamification (GAM)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/gam/internal/models/p1.py` | ORM: badges, user badges, tiers, leagues, members, challenges, progress, share cards | 160 |
| `modules/gam/internal/repositories/badges.py` | Definitions; awards | 70 |
| `modules/gam/internal/repositories/leagues.py` | Cohort creation; members; outcomes | 110 |
| `modules/gam/internal/repositories/challenges.py` | Challenges; progress | 90 |
| `modules/gam/internal/services/badge_rules.py` | Declarative rule evaluator (pure) | 140 |
| `modules/gam/internal/services/badges.py` | Award via ledger (kind `badge`) | 90 |
| `modules/gam/internal/services/leagues.py` | Assignment, weekly board keys, rollover | 160 |
| `modules/gam/internal/services/challenges.py` | Join, progress, completion | 130 |
| `modules/gam/internal/services/share_cards.py` | Payload by kind; privacy for minors; referral code | 110 |
| `modules/gam/internal/services/card_render.py` | Pillow renderer with bundled Bangla font | 120 |
| `modules/gam/internal/events/badge_consumers.py` | Handlers for `answer.recorded`, `session.completed`, `exam.submitted`, `reward.granted` | 100 |
| `modules/gam/internal/jobs/league_assign.py`, `league_rollover.py` | Saturday jobs | 70 each |
| `modules/gam/internal/routes/p1.py` | Badges, leagues, challenges, share cards | 120 |
| `modules/gam/internal/routes/admin_p1.py` | Badge and challenge admin | 80 |
| `modules/gam/internal/schemas/p1.py` | Schemas | 130 |

**CMS**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/cms/internal/models/p1.py` | ORM: AI drafts, author tasks, payouts | 80 |
| `modules/cms/internal/services/ai_drafts.py` | Request (enqueue AI job through the AI interface), decide → Draft version | 140 |
| `modules/cms/internal/services/coverage.py` | Coverage report, gap thresholds | 90 |
| `modules/cms/internal/services/author_pay.py` | Task capture from workflow events; payout run (audited) | 140 |
| `modules/cms/internal/events/author_task_consumer.py` | `question.published` and workflow events → tasks | 60 |
| `modules/cms/internal/routes/admin_p1.py` | AI drafts, reports, payouts | 110 |
| `modules/cms/internal/schemas/p1.py` | Schemas | 110 |

**Community (COM)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/com/internal/models/threads.py` | ORM: threads, posts, votes | 70 |
| `modules/com/internal/models/mentors.py` | ORM: requests, replies | 50 |
| `modules/com/internal/repositories/threads.py` | Thread by question; posts paginated; votes | 120 |
| `modules/com/internal/repositories/mentors.py` | Queue by SLA; replies | 90 |
| `modules/com/internal/services/threads.py` | Get-or-create thread, post with moderation, vote, pin | 150 |
| `modules/com/internal/services/mentors.py` | Escalate (credit debit), assign, reply, SLA breach | 160 |
| `modules/com/internal/jobs/mentor_sla.py` | SLA breach refund and notify | 60 |
| `modules/com/internal/routes/threads.py` | Thread routes | 90 |
| `modules/com/internal/routes/mentors.py` | Mentor routes | 90 |
| `modules/com/internal/schemas/p1.py` | Schemas | 120 |

**Identity (AUTH)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/auth/internal/services/promotion.py` | Promotion with history | 100 |
| `modules/auth/internal/routes/enrolments.py` (modify) | `:promote` | +30 |

**PAR and INST (contract only, D7-1)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/par/__init__.py` (modify) | `tutor_mode_lock(child_user_id)` returning `None` in B7 | +20 |
| `modules/inst/__init__.py` (modify) | `tutor_mode_lock_for_student(user_id)` (strictest across active batches) | +30 |
| `modules/inst/internal/repositories/batch_locks.py` | Read lock for a student's batches | 50 |
| `modules/inst/internal/routes/teacher_batches.py` (modify) | Teacher sets `tutor_mode_lock` on PATCH batch (existing B6 route extended) | +25 |

**Entry points**

| Path | Change |
|---|---|
| `entrypoints/api/app.py` (modify) | Mount new routers via each module's `routers()` |
| `entrypoints/workers/registry.py` (modify) | Register the new job kinds (§C.4) |
| `entrypoints/ai_gateway/app.py` (modify) | Mount AI P1 routers for streaming routes (quiz, coach use SSE) |

### C.4 Background jobs

| Job kind | Trigger | Idempotency |
|---|---|---|
| `qb.item_stats.compute` | Nightly 02:00 Dhaka | `dedupe_key = date`; upserts |
| `anl.time_analytics.compute`, `anl.trends.compute`, `anl.percentiles.compute` | Nightly; trends weekly | `dedupe_key = job:date`; upserts |
| `anl.forecast.compute` | Nightly per active enrolment (batched 1,000) | Upsert by PK |
| `prac.offline_pack.build` | On request | `dedupe_key = user:node:content_version` |
| `prac.offline_pack.revoke` | `entitlement.changed` consumer | `processed_events` |
| `ai.coach.replan` | Nightly | `dedupe_key = user:date` |
| `ai.misconception.scan` | Weekly | `dedupe_key = user:week` |
| `ai.summary.generate`, `ai.quiz.generate`, `cms.ai_draft.generate` | On request | Per-request id |
| `gam.badge.<event>` | Event consumers | `processed_events` + ledger key |
| `gam.league.assign` | Saturday 00:05 Dhaka | `dedupe_key = week_key` |
| `gam.league.rollover` | Saturday 00:01 Dhaka (before assign) | `dedupe_key = week_key` |
| `gam.challenge.progress` | Event consumers | `processed_events` |
| `plan.study_plan.remind` | Scheduled per item | `dedupe_key = item_id:remind_at` |
| `com.mentor.sla_check` | Every 5 min | Status guard |
| `cms.author_tasks.capture` | Event consumer | `processed_events` |
| `qb.compilation.pdf` | Monthly | `dedupe_key = month` |

### C.5 Caching

| Data | Cache | TTL and invalidation |
|---|---|---|
| Linked nodes | Process LRU + Redis `tax:links:{node}` | 1 h; invalidated on link write |
| Item rating | Redis `qb:rating:{qv_id}` | 24 h; refreshed by the stats job |
| Mastery map, analytics reads | Redis `anl:{metric}:{user}:{enrol}` | 1 h; mastery invalidated on answer |
| Published summaries | Redis by `(chapter, kind, lang)` (immutable per publish) | Until republish |
| League board | Redis sorted set `lb:league:{league_id}` | 35 days |

### C.6 Validation, errors and security

- Promotion: the target track must follow the source's track kind order (academic → admission → job), or be an allowed sibling (SSC → HSC) per `curriculum` config. Otherwise `422 invalid_promotion`.
- Mode change: if locked, `409 mode_locked` with `details.locked_by` (`guardian` or `teacher`).
- AI quiz from a photo: same moderation and image rules as photo solve; photos deleted after 30 days.
- Posts: `moderate()` returns `block` → `422 moderation_blocked`, or `review` → stored with `moderation_status='pending'` and hidden until reviewed. No DMs; mentor replies are visible only to the requester.
- Mentor escalation requires an active `mentor_credits` entitlement or quota; otherwise `402`-style `403 entitlement_required` with an upgrade link.
- Share cards for minors: first name only, no institution if `privacy_settings.profile_private`. The card URL is signed and expires in 7 days.
- Offline packs:
  - The pack key is wrapped with a key derived from the device session.
  - On revocation (refund, logout, session revoke), the next sync returns `pack_revoked`, and answers to it are still accepted and scored (v2 §6.5).
  - Packs never include exam questions.
- Warehouse jobs run with an IAM role that is read-only on the event-log bucket.

### C.7 Configuration

New `runtime_config` keys (seeded by migration, editable through the B1 admin endpoint):
- `prac.policy`, `prac.elo`
- `prac.daily_mix.mix` (default `{"review":0.4,"weak":0.4,"new":0.2}`)
- `anl.mastery.rules_version`
- `gam.league.size` (30) and `gam.league.promote` / `gam.league.relegate` (5)
- `com.mentor.sla_minutes` (default 720)
- `prac.offline.max_age_days` (30) and `prac.offline.effective_window_hours` (72)

New settings:
- `WAREHOUSE_BUCKET`
- `DUCKDB_MEMORY_LIMIT`
- `SHARE_CARD_BUCKET`

---

## D. API contracts

Global conventions (envelope, errors, pagination, rate tiers, idempotency) are in [`14`](14_api_contracts.md) §1. All endpoints use `Authorization: Bearer` unless marked otherwise. "Owner" checks run in the service layer.

### D.1 Practice and analytics

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/practice/reviews/due` | `?enrolment_id&limit&cursor` | `Page<{card_id, card_type, question_id, flashcard_id, due_at, overdue_days}>` + `due_count` | User; own cards | `limit ≤ 100` | 404 enrolment not owned | T-read / – |
| `POST /v1/practice/daily-mix` | `{enrolment_id}` | `{session_id, created: bool, composition: {review, weak, new}, items: QuestionPayload[]}` | Owner of enrolment | Enrolment active | 404, 409 `enrolment_closed` | T-write / R |
| `POST /v1/practice/diagnostic` | `{enrolment_id}` | `{session_id, items: QuestionPayload[], blueprint_id}` | Owner | One open diagnostic per enrolment | 409 `diagnostic_open`, 404 `no_blueprint` | T-write / R |
| `GET /v1/practice/abilities` | `?enrolment_id&node_id` | `{items: [{node_id, rating, uncertainty, attempts, band}]}` | Owner | – | 404 | T-read / – |
| `POST /v1/practice/sessions` (existing; new kinds) | adds `kind ∈ {review, speed_drill}`, `per_question_seconds` (speed drill, 10–120) | as B3 | as B3 | `per_question_seconds` only for speed drill | 422 | T-write / R |
| `GET /v1/progress/mastery` | `?enrolment_id&root_node_id` | `{levels: [{node_id, level, score}], legend}` | Owner | – | 404 | T-read / – |
| `GET /v1/progress/time-analytics` | `?enrolment_id&period=7d|30d|all` | `{per_subject: [...], rushed_pct, slow_pct, guess_pct, negative_loss_marks, computed_at}` | Owner | Period allow-list | 404, `204` while not yet computed | T-read / – |
| `GET /v1/progress/trends` | `?syllabus_version_id&subject_node_id&source_kind` | `{chapters: [{node_id, frequency_by_year, most_asked_rank, predicted_importance}], computed_at}` | User | – | 404 | T-read / – |
| `GET /v1/progress/percentile` | `?enrolment_id&metric=accuracy|xp|exam_score&scope=national|district` | `{percentile, cohort_size, computed_on}` (cohort < 50 → `insufficient_data`) | Owner | Allow-lists | 404 | T-read / – |
| `GET /v1/progress/forecast` | `?enrolment_id` | `{exam_date, projected_readiness, band: {low, high}, pace, needed_pace}` | Owner | Exam date known | 404 `no_exam_date` | T-read / – |

### D.2 Question bank, curriculum and CMS

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/nodes/{node_id}/links` | – | `{links: [{node_id, track_id, name_bn, name_en, weight}]}` | Public | – | 404 | T-read / – |
| `POST /v1/admin/topic-links` | `{node_a_id, node_b_id, weight 0.1–1.0}` | `{node_a_id, node_b_id, weight}` | Staff:curriculum (audited) | Different tracks; not same node; normalised order | 409 exists, 422 | T-admin / R |
| `DELETE /v1/admin/topic-links/{id}` | – | 204 | Staff:curriculum | – | 404 | T-admin / – |
| `POST /v1/admin/question-families` | `{name, concept_node_id, question_ids[]}` | `{id, name, question_count}` | Role:content.author | Same type and primary node | 422 `family_mismatch` | T-admin / R |
| `PATCH /v1/admin/question-families/{id}` | `{name?, add_question_ids?, remove_question_ids?}` | Family | Role:content.author | As above | 404, 422 | T-admin / R |
| `POST /v1/admin/flashcard-decks` | `{node_id, title, cards: [{front, back}]}` (≤ 500) | `{id, card_count}` | Role:content.author | KaTeX render check | 422 | T-admin / R |
| `PATCH /v1/admin/flashcard-decks/{id}` | Partial; `status` | Deck | Role:content.author | – | 404 | T-admin / R |
| `GET /v1/flashcard-decks` | `?node_id&mine=bool&cursor` | `Page<{id, title, source, card_count}>` | User (entitlement-filtered) | – | – | T-read / – |
| `POST /v1/flashcard-decks` | `{node_id, title, cards[]}` (≤ 200) | Deck | User | Moderated text | 422 `moderation_blocked` | T-write / O |
| `POST /v1/admin/current-affairs` | `{item_date, category, title_bn, body_bn, source_url}` | Item (status `draft`) | Role:content.author | URL allow-list scheme | 422 | T-admin / R |
| `PATCH /v1/admin/current-affairs/{id}` | Partial; `status: published` requires reviewer | Item | Role:content.author / content.publish | – | 404, 403 | T-admin / R |
| `GET /v1/current-affairs` | `?from&to&category&cursor` | `Page<item>` + `compilations[]` | User (job-track entitlement) | Range ≤ 31 days | 403 `entitlement_required` | T-read / – |
| `GET /v1/questions/{question_version_id}/stats` | `?window=all|90d` | `{attempts, p_value, discrimination, distractor_pct, avg_time_ms, probable_wrong_key, computed_at}` | Role:content.read | – | 404 | T-admin / – |
| `POST /v1/admin/ai-drafts` | `{kind: explanation|variant|translation|tag|wrong_key, question_id, options}` | `{id, status: pending}` | Role:content.author | Kind allow-list; one pending per (kind, question) | 409 | T-admin / R |
| `POST /v1/admin/ai-drafts/{id}:decide` | `{decision: accept|reject, edits?}` | `{id, status, created_version_id?}` | Role:content.author | Accept creates a Draft version, never Published | 409 `already_decided` | T-admin / R |
| `GET /v1/admin/reports/coverage` | `?syllabus_version_id&subject_node_id` | `{nodes: [{node_id, by_type, by_difficulty, verified, published, gap: bool}]}` | Role:content.read | – | 404 | T-admin / – |
| `GET /v1/admin/reports/authors` | `?period=YYYY-MM&author_id?` | `{authors: [{author_id, tasks, accepted, rate_total_poisha, payout_status}]}` | Staff:content.finance | – | – | T-admin / – |
| `POST /v1/admin/author-payouts:run` | `{period}` | `{payouts_created, total_poisha}` | Staff:content.finance (audited) | Period closed (past month) | 409 `already_run` | T-admin / R |
| `POST /v1/admin/concept-notes` (existing; new kinds) | `kind ∈ {concept, cheat_sheet, formula_sheet}` | As B2 | As B2 | – | – | T-admin / R |

### D.3 AI

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `PUT /v1/tutor/threads/{id}/mode` | `{mode: direct|socratic}` | `{mode, locked_by: null|guardian|teacher}` | Owner | – | 409 `mode_locked`, 404 | T-write / – |
| `POST /v1/ai/quizzes` | `{source: topic|notes|photo, node_id?, notes_text? (≤ 4,000 chars), photo_upload_id?, count 5–20, lang}` | SSE: `progress` events, then `final {quiz_id, session_id, items_label: "AI"}` | User; quota `ai_quiz_per_day` | Moderation; exam lock; source-specific fields | 423 `locked_exam`, 429 `quota_exhausted`, 422 | T-ai / R |
| `GET /v1/ai/summaries/{chapter_node_id}` | `?kind&lang` | `{kind, lang, body_html, reviewed_at, citations[]}` | User (entitlement for the chapter) | Kind allow-list | 404 `not_published` | T-content / – |
| `POST /v1/ai/coach/plan` | `{enrolment_id, hours_per_day 0.5–8, rest_days[], start_on}` | SSE then `final {coach_plan_id, items: [study_plan_item]}` | Owner | Exam date exists | 404 `no_exam_date`, 429 | T-ai / R |
| `GET /v1/ai/misconceptions` | `?enrolment_id&subject_node_id` | `{clusters: [{id, label, node_id, evidence_count, fix_session_id}]}` | Owner | – | – | T-read / – |
| `POST /v1/admin/ai/summaries/{id}:review` | `{decision: publish|reject, edits?}` | Summary | Role:content.triage (audited) | – | 409 | T-admin / R |

### D.4 Planner

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/study-plan/items` | `?from&to` (≤ 62 days) | `{items: [...]}` | User | Range | 422 | T-read / – |
| `POST /v1/study-plan/items` | `{enrolment_id, plan_date, kind, node_id?, minutes 5–480, remind_at?}` | Item | Owner of enrolment | `remind_at` in the future | 422 | T-write / O |
| `PATCH /v1/study-plan/items/{id}` | Partial; `status ∈ {planned, done, skipped}` | Item | Owner | – | 404 | T-write / – |
| `DELETE /v1/study-plan/items/{id}` | – | 204 | Owner | – | 404 | T-write / – |

### D.5 Gamification

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/badges` | – | `{earned: [{code, name, icon, awarded_at}], available: [{code, name, icon, progress?}]}` | User | – | – | T-read / – |
| `GET /v1/leagues/current` | `?track_id` | `{league_id, tier, week_key, ends_at, standings: [{rank, display_name, institution?, xp, is_me}], promote_zone, relegate_zone}` | User | Privacy rules applied | 404 `not_in_league` | T-read / – |
| `GET /v1/challenges` | `?track_id&status=active|joined|completed` | `{items: [{id, title, starts_at, ends_at, goal, reward, progress?}]}` | User | – | – | T-read / – |
| `POST /v1/challenges/{id}:join` | – | `{challenge_id, joined_at, progress}` | User | Window open; track match | 409 `already_joined`, 410 `expired` | T-write / O |
| `POST /v1/share-cards` | `{kind: result|streak|rank, ref_id?}` | `{card_id, image_url (signed, 7 d), share_text, referral_url}` | User (owner of ref) | Ref exists and is owned | 404, 403 | T-write / R |
| `POST /v1/admin/gam/badges` / `PATCH …/{code}` | `{code, name_bn, name_en, icon, rule, is_active}` | Badge | Staff:gam.rules (audited) | Rule JSON validated against the rule schema | 422 `invalid_rule` | T-admin / R |
| `POST /v1/admin/gam/challenges` / `PATCH …/{id}` | `{title_bn, title_en, track_id, starts_at, ends_at, goal, reward}` | Challenge | Staff:gam.rules (audited) | `ends_at > starts_at`; reward ≤ config maximum | 422 | T-admin / R |

### D.6 Community

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/questions/{question_id}/thread` | `?cursor&sort=top|new` | `{thread_id, pinned_post?, posts: Page<post>}` | User (question visible to the user) | – | 404 | T-read / – |
| `POST /v1/threads/{thread_id}/posts` | `{body (1–2,000 chars), media_upload_id?}` | `{post_id, moderation_status}` | User; not muted or banned | `moderate()` | 422 `moderation_blocked`, 403 `restricted` | T-write / O |
| `POST /v1/posts/{post_id}/vote` | `{value: 1|0}` | `{upvotes}` | User; not own post | – | 409 `own_post` | T-write / – |
| `POST /v1/posts/{post_id}:pin` | – | `{thread_id, pinned_post_id}` | Role:teacher.verified (subject scope) | Post in the subject | 403 | T-write / – |
| `POST /v1/mentor-requests` | `{tutor_message_id, note? ≤ 500}` | `{id, status, sla_due_at}` | Owner of the message; mentor credit available | One open request per message | 403 `entitlement_required`, 409 | T-write / R |
| `GET /v1/mentor-requests/{id}` | – | `{id, status, replies: [...]}` | Owner | – | 404 | T-read / – |
| `GET /v1/mentor/queue` | `?subject_node_id&cursor` | `Page<{request_id, subject, age_min, sla_due_at, question_preview}>` | Role:mentor (Teacher role + `mentor.reply` permission) | – | – | T-read / – |
| `POST /v1/mentor/requests/{id}/replies` | `{kind: text|image|voice, body?, media_upload_id?}` | `{reply_id}` | Assigned mentor | Media type and size by kind | 409 `not_assigned` | T-write / O |

### D.7 Identity

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/me/enrolments/{id}:promote` | `{target_track_id, exam_year, group_code?, version_lang?}` | `{closed_enrolment_id, new_enrolment: Enrolment}` | Owner | Allowed promotion path; no active duplicate | 422 `invalid_promotion`, 409 `already_enrolled` | T-write / R |

### D.8 Offline packs (proposed, §G.1)

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/practice/offline-packs` | `{enrolment_id, chapter_node_id}` | `{pack_id, status: building|ready, expires_at}` | Owner; entitlement covers the chapter | ≤ 10 active packs per user | 403 `entitlement_required`, 409 `limit_reached` | T-write / R |
| `GET /v1/practice/offline-packs` | – | `{items: [{pack_id, chapter_node_id, status, expires_at, download_url?, wrapped_key?}]}` | User | – | – | T-read / – |

---

## E. Testing strategy

Markers and fixtures as in [`15`](15_testing_and_quality_standards.md). The warehouse tests use a local Parquet fixture directory (`tests/fixtures/eventlog/`) and DuckDB in-process.

| Kind | Files | Cases |
|---|---|---|
| Unit (pure) | `tests/shared/test_fsrs.py` | FSRS intervals match the reference vectors for again, hard, good and easy; stability monotonic on good |
| Unit | `tests/shared/test_elo.py` | Expected-score symmetry; K switch at 30 attempts; rating bounds |
| Unit | `tests/modules/prac/unit/test_policy_elo.py` | Picks items in the 60–75% band; falls back to rule-based with sparse history; no item repeated within 24 h; excludes other tenants' items |
| Unit | `tests/modules/prac/unit/test_daily_mix_composer.py` | 40/40/20 with enough supply; redistributes when reviews are short; deterministic for a seed |
| Unit | `tests/modules/anl/unit/test_mastery_rules.py` | Table-driven level boundaries; linked-node propagation cap (D7-5) |
| Unit | `tests/modules/gam/unit/test_badge_rules.py` | Rule evaluator on counters and event predicates; invalid rule rejected |
| Unit | `tests/modules/gam/unit/test_league_outcomes.py` | Promote top 5 and relegate bottom 5; ties by earlier XP time; cohorts of 30 with remainder handling |
| Unit | `tests/modules/anl/unit/test_forecast.py` | Pace math; band widens with fewer data points |
| Integration (DB) | `tests/modules/prac/integration/test_answer_projections_p1.py` | One answer updates ability, review card and mastery in the same transaction; savepoint failure keeps the answer |
| Integration | `tests/modules/prac/integration/test_daily_mix_once.py` | Two concurrent creates → one session (marker `concurrency`) |
| Integration | `tests/modules/gam/integration/test_league_rollover.py` | Rollover twice → one outcome set; ledger keys unique; next-week leagues created |
| Integration | `tests/modules/gam/integration/test_badge_replay.py` | Replayed event → no second badge, no second ledger row |
| Integration | `tests/modules/qb/integration/test_item_stats_job.py` | Parquet fixture → expected p-value and discrimination; wrong-key flag opens one CMS error report (idempotent) |
| Integration | `tests/modules/anl/integration/test_warehouse_jobs.py` | Each job on fixtures; partition pruning (asserts the file list read) |
| Integration | `tests/modules/auth/integration/test_promotion.py` | History rows keep the old enrolment; the new enrolment is linked; duplicate refused |
| Integration | `tests/modules/com/integration/test_mentor_sla.py` | SLA breach refunds the credit exactly once |
| API | `tests/modules/*/api/test_*_p1.py` (one per router) | Every endpoint in §D: 200/201 path, validation errors, 404 for others' resources, rate tier headers |
| Authorization | `tests/modules/com/api/test_thread_authz.py`, `tests/modules/ai/api/test_mode_lock.py`, `tests/modules/prac/api/test_offline_authz.py` | Muted user cannot post; pin needs a verified teacher in the subject; a teacher lock overrides the student; pack refused without entitlement |
| Regression | Full B3–B6 suites unchanged | Answer replay and the 1M synthetic replay harness from B3 still produce identical projections (now including ability, mastery and review cards) |
| Edge | `tests/modules/prac/unit/test_offline_sync_window.py` | Answer at 71 h 59 m uses device time; at 72 h 01 m uses receipt time; answer to a retired version is scored against the version answered |
| Edge | `tests/modules/gam/integration/test_provisional_settlement.py` | Pack user misses day D: provisional `missed` at 06:00, then 5 answers effective on D arrive at D + 48 h → D becomes `counted` and the streak length is restored. Provisional `frozen` → `counted` returns the freeze through a reversing ledger row. After the 72 h finalisation no change is possible. A user without a pack is unaffected (final at 06:00). |
| AI eval | `tests/eval/test_socratic_gate.py` etc. (marker `eval`) | Socratic never reveals the key within the first two turns (≥ 95%); quiz items valid and on-syllabus (≥ 90%); summaries cite (100%); coach plans fit the hours (100%) |
| AI safety | `tests/modules/ai/integration/test_ai_items_isolation.py` | AI items never appear in `qbank` queries, search, similar questions, mastery or leaderboards |
| Privacy | `tests/modules/gam/api/test_share_card_privacy.py` | Minor's card shows first name only; opt-out respected |
| Failure | `tests/modules/nfr/integration/test_duckdb_failure.py` | Missing partition → job logs and skips; S3 unavailable → retry then dead job |
| Performance | `tests/load/b07_answer_path.js` (k6, not in CI) | Answer p95 DB time increase ≤ 3 ms vs the B6 baseline at Stage 1 load |
| Boundary | `scripts/check_boundaries.py` | AI does not import QB internals; `ai-gateway` DB role has no write grant on `qbank` |

**Coverage:** ≥ 85% overall. ≥ 95% on `shared/fsrs.py`, `shared/elo.py`, `prac/internal/services/{policy_elo,daily_mix,answer_projections_p1,offline_sync}.py`, `anl/internal/services/mastery_rules.py`, and `gam/internal/services/{badge_rules,leagues,badges,challenges}.py`.

---

## F. Build completion

### F.1 Acceptance criteria

1. All 34 IDs in §A.1 are demonstrated by API tests, and the traceability matrix rows for them point to passing test files.
2. Adaptive sessions keep the predicted success of selected items in 60–75% for ≥ 80% of selections on the synthetic population.
3. The 1M-answer replay (5% duplicates, reordering) produces identical `ability_estimates`, `review_cards` and `mastery_state` across two runs.
4. Daily Mix: exactly one session per (user, enrolment, Dhaka date) under 50 concurrent requests.
5. League rollover run twice produces one set of outcomes and one ledger row per user.
6. No AI-generated item, draft or summary is reachable from any verified-bank query (isolation test).
7. Warehouse jobs complete on the 30-day fixture in under 5 min on a 4 GB worker.
8. B3–B6 regression suites pass unchanged; answer-path p95 DB time rises by no more than 3 ms.
9. The eval gates for socratic-v1, quiz-v1, summary-v1, coach-v1 and misconception-v1 pass and are recorded in `ai.eval_runs`.
10. **Synthetic-data acceptance (R-29).** Under the backend-before-frontend rule, no real users exist before B9, so the data-hungry features are accepted on a seeded synthetic population: 20,000 simulated learners with known latent ability per topic, items with known difficulty and discrimination, and 8 weeks of simulated attempts generated by an IRT 2PL response model. The criteria:
    - **QB-11:** recovered p-value within ±0.05 and discrimination within ±0.10 of the generating values for items with ≥ 200 attempts; seeded wrong-key items flagged with ≥ 90% recall at ≤ 5% false positives.
    - **PRAC-08 (Elo):** the rank correlation between estimated and latent ability is ≥ 0.8 after 30 attempts per topic.
    - **ANL-07:** percentiles computed from the warehouse job match an exact computation over the fixture within ±1 percentile point.
    - **ANL-08:** the forecast's mean absolute error on held-out simulated weeks is reported, and below "insufficient data" thresholds the API says so.
11. **Post-launch calibration gate (R-29).** After 8 weeks of real traffic past launch, re-run the same metrics on real data:
    - Item statistics: bootstrap stability.
    - Elo: predicted versus observed success within the 60–75% band for ≥ 70% of selections.
    - Percentiles: sanity checks.
    - Forecasts: back-tested.

    Until this gate passes, the features are labelled "beta" in API responses (`calibration: "synthetic"`). Owner: the data/AI engineer. The gate is tracked in [`20`](20_risk_register.md).

### F.2 Deliverables

Migrations `b07_01`–`b07_16`; module code per §C.3; job registrations; prompt files and eval set pointers; seed data for TAX-05; updated OpenAPI snapshot; the build report in the PR.

### F.3 Definition of done

Per [`21`](21_definition_of_done.md): zero ruff, format and mypy errors; zero failing tests; zero 200-line violations; boundary and import-linter checks pass; `alembic check` clean; coverage thresholds met; OpenAPI diff reviewed; runbook entries added for the league rollover and warehouse job failures.

### F.4 Manual verification checklist

- [ ] Start a lesson for a user with history; confirm via the debug endpoint (staff) that the policy is `elo` and the items' predicted success is in band.
- [ ] Wrong answer → a review card appears in `reviews/due` on the expected date (frozen clock).
- [ ] Request Daily Mix twice → the same `session_id`.
- [ ] Promote SSC 2028 → HSC 2030; old history still visible on the dashboard under the closed enrolment.
- [ ] Teacher sets a Socratic lock on a batch; a student's `PUT mode` returns `409 mode_locked`.
- [ ] Generate an AI quiz; items show the "AI" label; completing grants +10 XP only, with no mistake entry.
- [ ] Trigger badge, challenge and league rollover in staging with a fake clock; inspect the ledger.
- [ ] Post with a profane Banglish word → blocked; mentor request → mentor reply → student sees it.
- [ ] Build an offline pack, revoke the entitlement, and sync answers → answers accepted, pack marked revoked.

### F.5 Exit criteria before Build 8

All of F.1–F.4 are done; QB-10 families exist and are usable by EXAM (`qb.family_of()`); the PAR public function `tutor_mode_lock` exists (for B8 to implement); supervisor sign-off on the §G proposed additions recorded in `01`/`14`.

---

## G. Proposed additions (accepted)

All items were **accepted** during integration and are now in [`01`](01_database_design.md) §3 and §4.E and in [`14`](14_api_contracts.md). The `family_plan` and `reward_store` entitlement sources are the final names.

| # | Addition | Why | Change |
|---|---|---|---|
| G.1 | Table `practice.offline_packs` (`id`, `user_id`, `track_enrolment_id`, `chapter_node_id`, `entitlement_id`, `content_version` text, `bundle_key`, `key_ciphertext bytea`, `status` (building, ready, revoked, expired), `expires_at`, `created_at`; ix `(user_id, status)`). Endpoints `POST` and `GET /v1/practice/offline-packs`. | OFF-03 needs pack lifecycle and revocation; no table or endpoint exists | Add to `01` §3.9 (B7) and `14` §3.6 (B7) |
| G.2 | Column `institution.batches.tutor_mode_lock text NULL` (`CHECK IN ('socratic','direct')`) | AI-06 teacher lock; v2 §4.9 says "a lock set by a parent or teacher" | Add to `01` §3.15 |
| G.3 | Session kinds `review` and `ai_quiz` in `practice.practice_sessions.kind` | PRAC-09 review sessions; AI-08 quizzes run as normal sessions | Add to the `01` §4 practice spec |
| G.4 | Product kind `mentor_credits` in `commerce.products.kind` | COM-02 is a paid escalation | Add to the `01` §4 commerce spec |
| G.5 | Endpoint `GET /v1/nodes/{node_id}/concept-notes` (list notes, cheat and formula sheets for a topic) | QB-12 needs a list by topic; `14` has only get-by-id | Add to `14` §3.5 (B7) |
| G.6 | Quota feature `ai_quiz_per_day` in `commerce.quota_policies.feature` | AI-08 cost control | Add to the `01` §4 commerce spec |

**Inconsistency noted:** `14` writes "Role:mentor" while AUTH-03 defines eight roles without a mentor. This build treats mentor as the Teacher role plus the permission `mentor.reply` (seeded in `identity.permissions`), which needs no new role.

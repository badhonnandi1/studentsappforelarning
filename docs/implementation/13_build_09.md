# 13 · Build 9: P2 expansion and scale certification

**Build:** 9 of 9 · **Priority band:** P2, plus scale certification · **Date:** 2026-11-27 · **Depends on:** Builds 1–8 merged and green · **Unblocks:** the frontend phase. At the end of this build the backend covers all 180 IDs.
**Read first:** [`04_backend_master_plan.md`](04_backend_master_plan.md), [`01_database_design.md`](01_database_design.md) §3 and §5 (especially §5.6 retention, §5.9 replicas, §5.12 bottlenecks), [`14_api_contracts.md`](14_api_contracts.md), [`17_scalability_and_performance.md`](17_scalability_and_performance.md), [`18_security_architecture.md`](18_security_architecture.md), [`19_devops_and_deployment.md`](19_devops_and_deployment.md), [`21`](21_definition_of_done.md)

---

## 0. How to run this build (coding-agent preamble)

1. Read the documents above. In `14`, every row with **B = 9** is in scope. In `01`, read the rows marked B 9, plus §5.
2. Confirm that Build 8 is complete:
   - `scripts/check.sh` passes on `main`;
   - `alembic current` is at the `b08_*` head;
   - RLS has been enabled in staging for at least 7 days.
3. Create the branch `build/09-expansion-scale`.
4. The build has **two tracks** that can run in parallel. They share only the migration sequence; take migration numbers in order from one list.
   - **Track 1, features:** §C.1 steps 1–17.
   - **Track 2, scale certification:** §C.1 steps 18–23. Track 2 changes no product behaviour.
5. The voice features (AI-12, AI-13, AI-14) each have an **eval gate**. If a gate fails, the feature ships behind a disabled flag and the build report says so. Never enable a voice feature that has not passed its gate.
6. Load tests run against a dedicated `perf` environment, never against shared staging during working hours. Their results go into `docs/capacity/` as dated reports. These reports are a deliverable of this build.
7. Verify §F, write the build report, and **stop**. This is the last backend build. Do not start frontend work.

---

## A. Overview

| Item | Value |
|---|---|
| Name | P2 expansion and scale certification |
| Objective | Implement the remaining 20 P2 requirements, and produce benchmark evidence for the scaling stages (1k, 10k, 50k and 100k concurrent learners; exams at 50k and 250k rehearsal) instead of claims |
| Business value | Social features (duels, groups, forum, follows), the B2B marketplace and white-label, sponsorships, voice learning, the rewards store, and the self-service privacy dashboard |
| Technical value | A new realtime deployable; replica routing; measured capacity per stage; a verified data-deletion pipeline |
| Complexity | 4 / 5. The features are extensions. The realtime service, voice evals, minor-safe group chat and the load programme carry the risk. |
| Effort | 16–24 backend person-weeks, of which 5–7 are scale certification **[Assumption]** |
| Modules | AUTH, CMS, PRAC, EXAM, ANL, AI, GAM, PLAN, COM, PAR, INST, PAY, NFR, plus the new `realtime` entry point |

### A.1 Features

| ID | Feature in this build |
|---|---|
| AUTH-10 | Under-18 parental consent dashboard (view, withdraw, re-consent); automated account export and deletion, replacing the support-driven P0 path from B6 |
| CMS-10 | Media library with CDN delivery, image compression variants and alt text |
| PRAC-13 | 1v1 real-time quiz duels (friend or random) and classroom group quiz rooms, served by the new `realtime` WebSocket deployable |
| EXAM-13 | Admission and job score predictor ("estimated position") from historical cut-offs |
| EXAM-14 | Proctored mode with random front-camera snapshots for institution exams that need it; consent and retention rules apply |
| ANL-09 | Exportable progress report PDF for parents and teachers |
| AI-12 | Voice: Bangla speech-to-text for questions; text-to-speech read-out of explanations |
| AI-13 | Spoken English partner with pronunciation feedback |
| AI-14 | Viva and interview simulator (BCS viva, BUP and AFMC interviews) with scored feedback |
| GAM-08 | Rewards store. Coins are earned alongside XP and spent on AI credits, discounts or merchandise. Levels and boards never go down. |
| GAM-09 | Friends and follow system; institution-vs-institution team leagues |
| PLAN-07 | WhatsApp and Telegram notification channels; Google Calendar export as an iCal feed |
| COM-03 | Subject Q&A forum |
| COM-04 | Study groups and batch chat with minor-safety controls (no DMs between minors and unknown adults; reporting; moderation) |
| PAR-05 | Parent alerts, e.g. "no study for 3 days" or "score dropped" |
| INST-09 | Teacher marketplace: teachers publish paid exam series or notes; revenue share; payouts |
| INST-10 | White-label subdomain and app configuration for large coaching chains |
| INST-11 | Attendance and basic fee tracking (light LMS) |
| PAY-08 | Scholarships and sponsored seats funded by NGOs or corporates |
| OFF-05 | Desktop-friendly web exam mode for institutions. **No backend work is needed.** The desktop exam uses the existing exam APIs, ingest and edge Worker unchanged. This build adds only an API compatibility test (§E). |

**Total: 20 P2 IDs.** With Builds 1–8 this completes all 180.

### A.2 Scale certification scope (Track 2)

| Item | Outcome |
|---|---|
| Read-replica routing | Declared read-only endpoints served from replicas, with a 1 s staleness budget (`01` §5.9) |
| Outbox relay throughput | Measured events per second per relay worker, and partition-parallel scaling to the Stage 4 target |
| Job-queue limits | Measured sustained jobs per second and claim latency. A written trigger for moving the hottest job kinds to SQS (v2 §0.2: about 1,000 jobs/s). |
| Learner load tests | 1k, 10k, 50k and 100k concurrent virtual learners on the workload model in `17`, with a report per stage |
| Exam rehearsal | 250,000 simulated candidates (1.25 × 200k) through the real edge and ingest path, with fault injection (v2 §6.4) |
| Capacity reports | `docs/capacity/YYYY-MM-DD-stage-N.md`: infrastructure used, measured limits, bottleneck found, next trigger |

### A.3 Dependencies

| Needs | From |
|---|---|
| Consent records, data-request workflow, Apple revocation | B1, B6, B8 |
| Question payloads, sessions, `attempt_answers` | B2, B3 |
| Ledger, friend links, boards | B3, B7 |
| AI provider layer, eval harness, quotas | B4 |
| Exam engine, ingest, load harness at 20k | B5 |
| PDF renderer, entitlements, products, payouts | B6, B7 |
| Workspaces, RLS, rosters, batches, parent links | B8 |

### A.4 Risks and blockers

| Risk | Mitigation |
|---|---|
| Bangla speech-to-text quality is unknown **[Needs evidence]** | A separate eval set (300 utterances across dialects, consented). The gate is a word error rate threshold set by the AI/ML lead before build start (proposed ≤ 25% for question capture). The feature stays behind a flag until it passes. |
| Minor safety in groups and forums | Group membership rules in the server (§C.2 D9-4). No 1:1 messaging anywhere. All text is moderated. Report and mute. Adults may join a minors' group only when it is institution-managed by a verified teacher. |
| Proctoring photos are sensitive data under PDPA 2026 (face images) | Opt-in per exam with specific consent (`guardian_consents.scope` includes `proctoring`). Images kept 30 days after merit is final, then deleted. Access only for that institution's exam staff, and audited. Pending D4. |
| Marketplace payouts need KYC and tax handling **[Needs evidence]** | Payout accounts start in `unverified` and are blocked until ops verification. Payout runs are manual-approved. Legal and finance sign-off is a precondition for enabling the flag. |
| WhatsApp Business API cost and template approval **[Needs evidence]** | Behind a flag. Transactional templates only. Cost tracked per message, like SMS. |
| A load test that is too cheap gives false confidence | Use the real edge path, a realistic payload size and realistic think times from the B3–B8 telemetry. Report p50, p95 and p99 plus error rates, never a single number. |
| A realtime service at scale | Sticky-free design (Redis pub/sub). Per-instance socket limits measured. Rooms capped at 200 participants. |

---

## B. Database implementation

### B.1 Tables to create

All tables come from `01` §3.

| Schema.table | Feature |
|---|---|
| `cms.media_assets` | CMS-10 |
| `practice.duel_rooms`, `duel_participants`, `duel_rounds`, `duel_answers` | PRAC-13 |
| `exam.proctor_snapshots` | EXAM-14 |
| `exam.cutoff_history`, `score_predictions` | EXAM-13 |
| `analytics.report_exports` | ANL-09 |
| `ai.voice_sessions`, `ai.viva_scenarios` | AI-12, AI-13, AI-14 |
| `rewards.store_items`, `redemptions`, `coin_balances`, `follows`, `team_leagues`, `team_scores` | GAM-08, GAM-09 |
| `notify.channel_bindings`, `calendar_feeds` | PLAN-07 |
| `community.forum_categories`, `study_groups`, `group_members`, `group_messages` (partitioned) | COM-03, COM-04 |
| `parent.alert_rules`, `alert_events` | PAR-05 |
| `institution.marketplace_listings`, `payout_accounts`, `payouts`, `whitelabel_configs`, `attendance_records`, `fee_records` | INST-09, INST-10, INST-11 |
| `commerce.sponsors`, `sponsorships`, `sponsored_seats` | PAY-08 |
| `ai.voice_turns` | **Proposed** (G.3) |

### B.2 Tables to modify

| Table | Change |
|---|---|
| `rewards.reward_transactions` | `kind` check gains `coins` (if not already present); coins are earned in the B3 answer savepoint through a rule in `reward_rules` (new rule version) |
| `rewards.coin_balances` | Created in this build; it is the only coin balance, with `CHECK (coins >= 0)` for spends. `user_totals` has no coin column (01 §4.B, PB-2). Coin rows use the `reward_keys.coins_*` builders (`coins:{xp_idempotency_key}`, `coins:spend:{redemption_id}`), never a hand-built key (R-05). |
| `community.threads` | `scope` value `forum` and a non-null `node_id` for forum threads (column exists) |
| `practice.attempt_answers` | None: `duel` is already in the canonical B3 `context` CHECK (`practice_learn`, `practice_test`, `written_self`, `exam_live`, `exam_practice`, `exam_reattempt`, `duel`; R-32). Duel answers are inserted with `context='duel'`. |
| `commerce.entitlements` | `source` check gains `reward_store` and `scholarship` (if not already present) (G.5) |
| `commerce.quota_policies` | `feature` values `voice_minutes_per_day`, `spoken_english_minutes_per_day`, `viva_sessions_per_week` (G.6) |
| `identity.data_requests` | `requested_via` gains `self_service`; `artifact_key` used for export ZIPs |
| `identity.guardian_consents` | `scope` keys `proctoring`, `voice`, `groups` (JSON, no DDL) |

### B.3 Migration sequence

| # | Revision | Content |
|---|---|---|
| 1 | `b09_01_cms_media_library` | `media_assets` |
| 2 | `b09_02_practice_duels` | Duel tables; `attempt_answers.context` widened |
| 3 | `b09_03_exam_proctor_predictor` | Proctor snapshots, cut-off history, predictions |
| 4 | `b09_04_analytics_reports` | Report exports |
| 5 | `b09_05_ai_voice` | Voice sessions, viva scenarios, voice turns (G.3) |
| 6 | `b09_06_rewards_store_follows` | Store items, redemptions, coin balances, follows, team leagues and scores; ledger kind widened; new rule version seeded |
| 7 | `b09_07_notify_channels` | Channel bindings, calendar feeds |
| 8 | `b09_08_community_forum_groups` | Forum categories, groups, members, messages (partitioned, 3 months ahead) |
| 9 | `b09_09_parent_alerts` | Alert rules and events |
| 10 | `b09_10_institution_marketplace` | Listings, payout accounts, payouts |
| 11 | `b09_11_institution_whitelabel_lms` | White-label configs, attendance, fees; RLS policies on the new tenant tables (enabled in the same migration, because these tables are new) |
| 12 | `b09_12_commerce_sponsorships` | Sponsors, sponsorships, sponsored seats; source and quota check widenings |
| 13 | `b09_13_partition_retention_p2` | Partition-maintenance entries for `group_messages`, retention rules for proctor and voice audio |

### B.4 Transaction and integrity requirements

| Operation | Requirement |
|---|---|
| Coin redemption | One transaction, in this order: (1) `UPDATE coin_balances SET coins = coins - :cost WHERE user_id=:u AND coins >= :cost RETURNING`; no row means `409 insufficient_coins`; (2) a ledger row of kind `coins` with a negative amount and key `redeem:{redemption_id}`; (3) the `redemptions` insert (user and idempotency key unique); (4) fulfilment. Fulfilment for AI credits grants an entitlement with source `reward_store`; for a discount it generates a single-use coupon. Then the outbox row. XP and levels are untouched. |
| Duel answer | Two steps. First, the realtime service validates the round window (server time) and writes `duel_answers` (PK `room_id, round_no, user_id`). Second, a job copies the answer through `prac.record_answer(session, …, context='duel')`, so the notebook, mastery and XP follow the normal rules, idempotent on `answer_id`. |
| Sponsored seat | `UPDATE sponsorships SET seats_used = seats_used + 1 WHERE id=:id AND seats_used < seats AND valid_to > now() RETURNING`, then the `sponsored_seats` insert and an entitlement with source `scholarship`, in one transaction |
| Marketplace payout | Monthly job. `gross` = captured payments minus refunds on listing products for the period. `share = gross × revenue_share_bps / 10,000` (floored poisha). The `payouts` row is unique on `(payout_account_id, period)`, approved by finance (audited), paid manually or through a provider. |
| Account deletion (AUTH-10) | A 7-day grace period, which the user can cancel, and a step-up OTP to request. Then the B6 event pipeline runs without manual approval: AUTH revokes sessions and the Apple token and emits `user.deletion_requested`. Each module's consumer anonymises its own rows and files per `01` §5.6, covering PII columns, external identities, push tokens, channel bindings, photos, submissions after the batch archive rule, voice audio and proctor snapshots. Each emits `user.deletion_completed{module}`. AUTH tracks `data_requests.module_status` and writes the audit and `completed_at` when all are done. Idempotent and resumable per module (R-03). |
| Export (AUTH-10) | `user.export_requested` → each module writes its JSON part (profile, enrolments, attempts, rewards, tutor threads, submission metadata, payments) and emits `user.export_part_ready` → AUTH zips the parts into the private bucket and signs a 24 h URL. It does not include other users' data, such as group messages from others. |
| Group message | `moderate()` runs before the insert. Blocked text is not stored, only logged in `moderation_decisions`. The membership check runs under the group's minor-safety rules (§C.2 D9-4). |
| Attendance | PK `(batch_id, roster_entry_id, class_date)` upsert; audited edits after 7 days |

---

## C. Backend implementation

### C.1 Steps in dependency order

**Track 1: features**

1. **CMS-10 media library.**
   - Upload through a presigned URL.
   - A worker produces variants (WebP at 320, 640 and 1280 px, plus the original) with Pillow, and runs the moderation check.
   - Alt text is required by the B8 rule.
   - Question media can reference `media_assets` by id; the existing `question_media` rows stay, with no migration of old rows.
2. **AUTH-10 privacy dashboard.**
   - Consent list, withdraw and re-consent. Withdrawing guardian consent for an under-18 user puts the account into restricted mode: no AI, no groups, no leaderboards, practice only, until consent is given again.
   - Self-service export and deletion jobs, replacing the B6 support path, which remains for staff.
3. **ANL-09 progress report PDF.** A requester can be the student, a linked guardian or a batch teacher. The content is the dashboard, mastery, exam history and weak areas. WeasyPrint with Bangla fonts. The signed URL expires after 7 days.
4. **EXAM-13 predictor.**
   - Import cut-off history from CSV (admin, audited).
   - The prediction model is a monotone mapping from score percentile in comparable mocks to an estimated position band, with a disclaimer.
   - It uses only `exam_results` from the same blueprint family.
5. **EXAM-14 proctoring.**
   - An exam flag `proctoring_required` (column in `exams.settings` jsonb, G.7) applies to institution exams only.
   - Specific consent is required before start.
   - Snapshot upload at random intervals (the client schedules them; the server rejects more than 1 per 2 minutes).
   - The tenant staff review queue is audited; deletion runs 30 days after merit is final.
6. **GAM-08 rewards store.**
   - A new `reward_rules` version adds coins earned with XP (proposed 1 coin per 10 XP, capped at 30 per Dhaka day **[Rule]**, configurable).
   - The store catalogue, redemptions and fulfilment adapters (AI credits, coupon, merchandise with a manual fulfilment queue).
7. **GAM-09.**
   - Follows are one-way. A follow gives no messaging and no profile beyond what the board shows.
   - Followed users appear in the friends board audience.
   - Team leagues: a weekly aggregation job per institution over `reward_transactions` by `recorded_at`. Members are counted only with verified roster links where available; otherwise the result is labelled "self-reported" (C15).
8. **COM-03 forum.** Categories per subject node; threads with `scope='forum'`, reusing the B7 thread and post services. Moderation and reporting as for B7.
9. **COM-04 study groups.** Groups, members and messages, all under the minor-safety rules (D9-4). Messages are retained for 12 months.
10. **PAR-05 alerts.** A rule engine over daily study and exam results. A nightly job writes `alert_events` and a PLAN notification, deduplicated per rule per day.
11. **PLAN-07 channels.**
    - Telegram: the bot binding flow uses a deep-link token, and the inbound webhook verifies the secret token.
    - WhatsApp: Cloud API template messages and an inbound webhook with a verify token (G.2).
    - iCal: a private feed token that serves study plan items, exam dates and followed tracker items.
    - All channels respect quiet hours and minors' rules.
12. **PRAC-13 realtime duels.**
    - Start a new `realtime` entry point: FastAPI WebSocket with authentication from the access JWT in the first message, plus Redis pub/sub per room.
    - Room lifecycle: create, join by code, lobby, rounds with a server-timed `closes_at`, scoring, results.
    - Random matching uses a Redis queue per (track, band), with a 30 s timeout that offers a bot-free fallback ("try again").
    - Classroom rooms are tenant-scoped (batch).
    - Answers are copied to `attempt_answers` by a job (§B.4).
13. **AI-12 voice.** STT and TTS provider adapters behind the B4 provider interface (provider chosen by eval **[Needs evidence]**). Uploaded audio is kept for 7 days. STT output feeds the normal tutor message pipeline. TTS reads verified explanations, and the audio is cached per `(question_version_id, lang, voice)`.
14. **AI-13 spoken English partner.** Session turns (G.3) with STT, the tutor model and pronunciation feedback (phoneme-level scores from the STT provider when available, otherwise word-level confidence). It has its own quota and safety prompts.
15. **AI-14 viva simulator.** Scenario rubrics (admin-authored). The session asks N questions and scores answers against the rubric with the top-tier model. The feedback is labelled "practice feedback" and is never a certification (Anthropic AUP: decisions about admission need human review).
16. **INST-09 marketplace.**
    - Listings are created by a workspace teacher and point to a product of kind `exam_series` or `notes` (G.8).
    - Content passes a platform review (CMS two-person workflow, `kind='marketplace_review'`) before it can be listed.
    - Payout accounts are verified by ops; the payout job and its reports follow.
17. **INST-10 white-label and INST-11 LMS.**
    - White-label: subdomain → workspace resolution at the edge (Cloudflare) and in `/v1/whitelabel/{subdomain}/config` (theme, logo, enabled features). Sign-in uses the same accounts.
    - Attendance and fee records, tenant-scoped under RLS.
    - **PAY-08 sponsorships:** sponsors, pools, criteria (district, class, need flag set by an institution), seat assignment.

**Track 2: scale certification**

18. **Read-replica routing.**
    - A second engine, `core/db_replica.py`, with a route-level dependency `read_replica_ok`.
    - It is allowed only on the endpoints in the allow-list (§C.3); `scripts/check_replica_routes.py` checks that list.
    - Replica lag is measured: lag above 1 s falls back to the primary, with a metric.
19. **Outbox relay scaling.** The relay claims partitions by hash of `aggregate_id` mod N, with N workers via lease rows in `relay_checkpoints` (one checkpoint per shard). Throughput is measured.
20. **Job-queue certification.**
    - Synthetic job load at 250, 500, 1,000 and 2,000 jobs/s; measure claim latency and table bloat.
    - Document the SQS trigger.
    - Implement an `SqsJobBackend` behind the job-runner protocol for one job kind (`gam.leaderboard.apply`), behind a flag. It is not enabled by default.
21. **Learner load programme.**
    - k6 scenarios from telemetry: home, session start, answers at a 40 s think time, dashboard, leaderboard, tutor (mocked provider at measured latency), photo solve (mocked).
    - Stages of 1k, 10k, 50k and 100k virtual users.
    - Pass criteria per `17`.
22. **Exam rehearsal at 250k.** Reuse the B5 harness with distributed generators. Cover the lobby, key release, synchronised start, 60 min of autosave at ceiling, 1% batch drops, 2% late answers, a consumer kill, an SQS throttle, a 10% reconnect storm, then hard close, contiguity, merit and the result-read rush.
23. **Capacity reports and alert tuning.** Write a report per stage. Update the autoscaling thresholds, PgBouncer pool sizes and alert thresholds from the measurements, as a config change with a PR.

### C.2 Design decisions

| # | Decision | Rationale |
|---|---|---|
| D9-1 | The realtime deployable uses Redis pub/sub, with no sticky sessions | Horizontal scaling without load-balancer affinity; room state is authoritative in Redis, with periodic snapshots to Postgres |
| D9-2 | Duel answers reach `attempt_answers` asynchronously | Keeps the socket loop free of the answer transaction. The B3 rules (24 h repeat, 300 XP cap) still apply because the same service is used. |
| D9-3 | Coins are a separate balance; spending never touches XP | v2 §5.7: "levels and boards never go down" |
| D9-4 | **Group minor safety.** (a) No 1:1 messages anywhere. (b) A group containing minors may include adults only if it is institution-managed (batch-linked, verified teacher) or every adult is a linked guardian of a member. (c) Joining requires an invite code from the owner. (d) Under-18 members need guardian consent with scope `groups`. (e) Images are moderated. (f) Report, mute and ban as for COM-05. | features.md COM-04, NFR-07, v2 §7.4 |
| D9-5 | Proctoring is opt-in per institution exam, needs specific consent, and has 30-day retention | PDPA 2026: face photos are sensitive data (market-validation) |
| D9-6 | Voice features use the provider interface; no self-hosted speech models in this build | Cost and quality are decided by eval, not reputation (v2 §0.4) |
| D9-7 | Replica reads are allowed only for routes with no read-your-writes requirement | Prevents stale reads after a write (e.g. reading an answer just saved) |
| D9-8 | The SQS job backend is implemented but disabled | Ready when the measured trigger is reached; no premature infrastructure |

### C.3 Files to create or modify

Paths are relative to `backend/src/app/` unless noted. Each file is ≤ 200 lines.

**Realtime deployable (PRAC-13)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `entrypoints/realtime/app.py` | `create_app("realtime")`, WebSocket route, readiness (Redis) | 70 |
| `entrypoints/realtime/__main__.py` | Uvicorn launch | 20 |
| `modules/prac/internal/realtime/connection.py` | Authentication on the first frame, heartbeat, backpressure (bounded send queue) | 130 |
| `modules/prac/internal/realtime/rooms.py` | Room state machine (Redis hash), pub/sub fan-out | 160 |
| `modules/prac/internal/realtime/rounds.py` | Server-timed rounds, answer validation, scoring | 140 |
| `modules/prac/internal/realtime/matching.py` | Random matching queue per band | 90 |
| `modules/prac/internal/models/duels.py` | ORM: rooms, participants, rounds, answers | 90 |
| `modules/prac/internal/repositories/duels.py` | Persistence and snapshots | 110 |
| `modules/prac/internal/services/duels.py` | Create, join, results (HTTP side) | 140 |
| `modules/prac/internal/jobs/duel_answer_copy.py` | Copy into `attempt_answers` via `record_answer` | 70 |
| `modules/prac/internal/routes/duels.py` | HTTP routes | 80 |
| `modules/prac/internal/schemas/duels.py` | HTTP and WS message schemas (discriminated union) | 130 |

**Identity, privacy and CMS**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/auth/internal/services/consent_dashboard.py` | List, withdraw, re-consent; restricted mode | 140 |
| `modules/auth/internal/services/data_export.py` | Export assembly from `user.export_part_ready` events (no imports of other modules) | 130 |
| `modules/auth/internal/services/data_deletion.py` | Grace period, cancel, auto-approval, `module_status` tracking and resume | 150 |
| `modules/auth/internal/jobs/data_requests.py` | Job handlers | 80 |
| `modules/auth/internal/routes/privacy.py` | Consent and data-request routes | 100 |
| `modules/*/internal/events/user_lifecycle.py` (modify; created in B6) | Cover the B7–B9 tables (voice, groups, proctoring, marketplace) in each module's deletion and export consumers | +20–40 each |
| `modules/cms/internal/models/media.py` | ORM | 40 |
| `modules/cms/internal/services/media_library.py` | Register, variants, alt text, search | 140 |
| `modules/cms/internal/jobs/media_variants.py` | Pillow variants | 90 |
| `modules/cms/internal/routes/media.py` | Routes | 70 |

**Exams, analytics and AI**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/exam/internal/models/p2.py` | Proctor snapshots, cut-offs, predictions | 70 |
| `modules/exam/internal/services/proctoring.py` | Consent check, rate rule, review, deletion | 140 |
| `modules/exam/internal/services/predictor.py` | Cut-off import and position-band model | 140 |
| `modules/exam/internal/routes/p2.py` | Proctor, predictions, cut-off import | 90 |
| `modules/anl/internal/models/reports.py` | Report exports | 30 |
| `modules/anl/internal/services/report_pdf.py` | Assemble and render | 150 |
| `modules/anl/internal/routes/reports.py` | Routes | 60 |
| `modules/ai/internal/providers/speech.py` | STT and TTS adapters (protocol plus one implementation) | 150 |
| `modules/ai/internal/services/voice.py` | Transcribe and speak, quotas, audio retention | 140 |
| `modules/ai/internal/services/spoken_english.py` | Sessions, turns, pronunciation feedback | 150 |
| `modules/ai/internal/services/viva.py` | Scenarios, turns, rubric scoring | 150 |
| `modules/ai/internal/models/voice.py` | Voice sessions, scenarios, turns | 70 |
| `modules/ai/internal/routes/voice.py` | Routes (served by `ai-gateway`) | 120 |
| `modules/ai/internal/prompts/spoken-english-v1.md`, `viva-v1.md` | Prompts | data |
| `tests/eval/sets/stt_bn_v1.yaml`, `spoken_en_v1.yaml`, `viva_v1.yaml` | Eval set pointers | data |

**Gamification, community, planner and parents**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/gam/internal/models/p2.py` | Store, redemptions, coin balances, follows, team leagues and scores | 120 |
| `modules/gam/internal/services/coins.py` | Coin earn rule in the savepoint; balance | 90 |
| `modules/gam/internal/services/store.py` | Catalogue, redemption, fulfilment adapters | 160 |
| `modules/gam/internal/services/follows.py` | Follow and unfollow, privacy | 70 |
| `modules/gam/internal/services/team_leagues.py` | Weekly aggregation | 120 |
| `modules/gam/internal/routes/p2.py` | Store, follows, team leagues | 100 |
| `modules/com/internal/models/groups.py` | Forum categories, groups, members, messages | 90 |
| `modules/com/internal/services/forum.py` | Forum on the B7 thread services | 90 |
| `modules/com/internal/services/group_safety.py` | D9-4 rules (pure) | 110 |
| `modules/com/internal/services/groups.py` | Groups, membership, messages | 160 |
| `modules/com/internal/routes/forum_groups.py` | Routes | 130 |
| `modules/plan/internal/providers/telegram.py`, `whatsapp.py` | Channel adapters | 110 each |
| `modules/plan/internal/services/channels.py` | Binding, routing, cost tracking | 130 |
| `modules/plan/internal/services/ical_feed.py` | iCal rendering (`icalendar`) | 90 |
| `modules/plan/internal/routes/channels.py` | Bind, unbind, feed, inbound webhooks (G.2) | 110 |
| `modules/par/internal/models/alerts.py` | Alert rules and events | 40 |
| `modules/par/internal/services/alerts.py` | Rule evaluation (pure) and job | 130 |
| `modules/par/internal/routes/alerts.py` | Routes | 70 |

**Institutions and commerce**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/inst/internal/models/p2.py` | Listings, payout accounts, payouts, white-label, attendance, fees | 130 |
| `modules/inst/internal/services/marketplace.py` | Listing lifecycle, platform review hand-off | 150 |
| `modules/inst/internal/services/payouts.py` | Revenue-share computation, approval | 140 |
| `modules/inst/internal/services/whitelabel.py` | Subdomain validation (reserved words, DNS label rules), config | 110 |
| `modules/inst/internal/services/lms.py` | Attendance and fees | 130 |
| `modules/inst/internal/routes/p2.py` | Routes | 160 |
| `modules/pay/internal/models/sponsorships.py` | Sponsors, pools, seats | 60 |
| `modules/pay/internal/services/sponsorships.py` | Pools, criteria, seat assignment | 140 |
| `modules/pay/internal/routes/sponsorships.py` | Admin routes | 70 |

**Scale certification**

| Path | Responsibility | ~Lines |
|---|---|---|
| `core/db_replica.py` | Replica engine, lag probe, fallback | 100 |
| `core/http_replica.py` | `read_replica_ok` dependency | 50 |
| `scripts/check_replica_routes.py` | Allow-list check | 80 |
| `modules/nfr/internal/relay/sharding.py` | Shard leases for the relay | 120 |
| `core/jobs/sqs_backend.py` | `SqsJobBackend` (flagged) | 140 |
| `tests/load/learner/*.js` | k6 scenarios: `home.js`, `session.js`, `answers.js`, `dashboard.js`, `boards.js`, `tutor_mock.js`, `mix.js` | ≤ 150 each |
| `tests/load/exam/*.js` | Distributed exam generator (k6, JavaScript, reusing the B5 `exam_clients.js`) plus fault injectors | ≤ 180 each |
| `tests/load/mocks/llm_mock.py` | Provider mock with measured latency distribution | 90 |
| `docs/capacity/README.md` and reports | Capacity reports (Markdown; not code, so not subject to the line rule) | – |

**Replica allow-list (initial):**
- `GET /v1/progress/*`
- `GET /v1/exams` and `GET /v1/exams/{id}/merit`
- `GET /v1/papers*`
- `GET /v1/search/questions`
- `GET /v1/admin/questions` (search)
- `GET /v1/admin/reports/*`
- `GET /v1/admin/bi/*`
- `GET /v1/tracker`
- `GET /v1/exam-series/{id}/standings`

Never on this list: entitlements, the answer path, session reads, payments, auth.

### C.4 Background jobs

| Job kind | Trigger | Idempotency |
|---|---|---|
| `auth.data_export.build`, `auth.data_deletion.run` | Request (deletion after the 7-day grace) | `data_requests.status` state machine |
| `cms.media.variants` | Upload confirm | `media_asset_id` |
| `anl.report.pdf` | Request | `report_export_id` |
| `exam.proctor.purge` | Daily | Status guard |
| `gam.team_league.aggregate` | Saturday 00:10 | `week_key` |
| `gam.store.fulfil` | Redemption | `redemption_id` |
| `par.alerts.evaluate` | Nightly | `alert_events.dedupe_key` |
| `plan.channel.deliver` | Notification fan-out | `deliveries` row |
| `prac.duel.copy_answers` | Round close | `answer_id` |
| `ai.voice.audio_purge` | Daily | Status guard |
| `inst.payouts.compute` | Monthly | `(payout_account_id, period)` |
| `nfr.partition.maintain` (extended) | Daily | Existing |

### C.5 Security and privacy

- Realtime:
  - The JWT is verified on connect and re-checked every 5 min. A revoked session closes the socket within 60 s (the `revoked_sess` Redis key).
  - Message rate: 5 per second per socket. Payload ≤ 4 KB.
- Voice audio and proctor snapshots are stored under `t/{tenant}/…` or `u/{user}/…` prefixes with lifecycle rules, and are never used for model training without separate consent (D4).
- White-label subdomains:
  - Validated against a reserved list and the DNS label grammar.
  - Tenant configs are public but contain no secrets.
- The marketplace requires a verified payout account before listing. Prices are set in poisha with a floor and ceiling from config.
- Export ZIPs are encrypted at rest. The link is single use, with a 24 h expiry. The download is audited.
- Inbound webhooks:
  - Telegram is authenticated by the `X-Telegram-Bot-Api-Secret-Token` header.
  - WhatsApp is authenticated by an `X-Hub-Signature-256` HMAC check.
- Load tests run against `perf` with synthetic accounts only, never with production data.

### C.6 Configuration

New settings:
- Speech: `SPEECH_PROVIDER`, `SPEECH_API_KEY`
- Channels: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `WHATSAPP_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`
- Replicas: `DATABASE_REPLICA_URLS`, `REPLICA_MAX_LAG_MS`
- Jobs: `JOB_BACKEND` (`postgres` | `sqs`), `SQS_JOB_QUEUE_URL`

New `runtime_config` keys:
- `gam.coins.rule`
- `com.groups.max_members`
- `prac.duel.round_seconds`
- `exam.proctor.min_interval_s`
- `ai.voice.enabled`, `ai.spoken_english.enabled`, `ai.viva.enabled`, which default to off until each eval gate passes

---

## D. API contracts

Conventions are in [`14`](14_api_contracts.md) §1.

### D.1 Privacy and data (AUTH-10)

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/me/consents` (G.1) | – | `{consents: [{id, kind, version, scope, granted_at, withdrawn_at, guardian_phone_masked}]}` | User, or a linked guardian for the child | – | – | T-read / – |
| `POST /v1/me/consents/{id}:withdraw` (G.1) | `{reason?}` | `{consent_id, withdrawn_at, account_mode: restricted|normal}` | User or the guardian (audited) | Active consent | 404, 409 `already_withdrawn` | T-write / R |
| `POST /v1/me/data-requests` (existing, now self-service) | `{kind: export|deletion, for_child_id?}` | `{request_id, status, due_at, cancel_until?}` | User, or a guardian for a linked child | One open request per kind | 409 `request_open` | T-write / R |
| `DELETE /v1/me/data-requests/{id}` (G.1) | – | `{status: cancelled}` | Owner, within the grace period | Deletion in grace | 409 `past_grace` | T-write / – |
| `GET /v1/me/data-export/{id}` | – | `302` to a signed URL (24 h, single use) | Owner | Export ready | 404, 410 `expired` | T-read / – |

### D.2 Media library (CMS-10)

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/admin/media` | `?q&mime&cursor` | `Page<{id, url_variants, alt_text_bn, alt_text_en, bytes}>` | Role:content.author | – | – | T-admin / – |
| `POST /v1/admin/media` | `{upload_id, alt_text_bn?, alt_text_en?}` | `{id, status: processing}` | Role:content.author | MIME allow-list (png, jpeg, webp, svg sanitised); ≤ 10 MB | 422 | T-admin / R |

### D.3 Duels (PRAC-13)

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/duels` | `{kind: duel|group, mode: friend|random|classroom, track_id, node_ids[], rounds 3–20, batch_id?}` | `{room_id, join_code, ws_url}` | User; classroom needs Role:teacher (batch) | Nodes in the user's enrolments | 422 | T-write / R |
| `POST /v1/duels/{code}:join` | – | `{room_id, ws_url}` | User; classroom needs a batch member | Room in lobby; < 200 participants | 404, 409 `room_started`, 409 `room_full` | T-write / – |
| `GET /v1/duels/{id}` | – | `{status, participants: [{display_name, score, rank}], rounds_played}` | Room member | – | 404 | T-read / – |
| `WS /v1/realtime/duels/{id}` | Client frames: `auth {token}`, `ready`, `answer {round_no, answer_id, response}`, `ping`. Server frames: `state`, `round_start {round_no, question: QuestionPayload, closes_at}`, `round_result {correct_label, scores}`, `final {results}`, `error {code}`. | – | Room member (JWT in the first frame) | Answer before `closes_at` (server time); one per round | `error: late`, `duplicate`, `not_member` | 5 msgs/s / per-round uniqueness |

### D.4 Exams and analytics

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/exam-attempts/{id}/proctor-snapshots` | `{upload_id, taken_at}` | `{accepted: true}` | Owner; exam has proctoring; consent with scope `proctoring` | ≥ 120 s since the last snapshot; attempt in progress | 403 `consent_required`, 429 | T-upload / R |
| `GET /v1/predictions` | `?target_kind&target_ref&exam_attempt_id?` | `{position_band: {low, high}, cutoff_year, confidence, disclaimer}` | User | Target known | 404 `no_cutoffs` | T-read / – |
| `POST /v1/admin/cutoffs:import` | `{upload_id}` (CSV: target, year, cutoff, seats, source_url) | `{rows_imported, errors[]}` | Staff:exam.manage (audited) | Schema | 422 | T-admin / R |
| `POST /v1/progress/reports` | `{subject_user_id?, enrolment_id, period}` | `{report_id, status}` | Self, linked guardian, or a teacher of the student's batch | Relation verified | 403 | T-write / R |
| `GET /v1/progress/reports/{id}` | – | `{status, pdf_url?, expires_at}` | Requester | – | 404 | T-read / – |

### D.5 AI voice (AI-12, AI-13, AI-14)

All are served by `ai-gateway`. All check the exam lock (423), the feature flag (`503 kill_switch` when off) and quotas (429).

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/ai/voice/transcribe` | `{upload_id, lang: bn|en, thread_id?}` | `{text, confidence, segments[]}`; with `thread_id`, also creates a tutor message (SSE) | User; consent scope `voice` for minors | Audio ≤ 60 s, ≤ 2 MB, opus or aac | 422, 423, 429 | T-ai / R |
| `POST /v1/ai/voice/speak` | `{question_version_id?, message_id?, lang, voice?}` | `{audio_url (signed), cached: bool}` | User; the source is accessible | Exactly one source | 404 | T-ai / O |
| `POST /v1/ai/spoken-english/sessions` | `{level: beginner|intermediate|advanced, topic?}` | `{session_id, opening_prompt_text, opening_audio_url}` | User | – | 429 | T-ai / R |
| `POST /v1/ai/spoken-english/sessions/{id}/turns` (G.3) | `{upload_id}` | SSE: `transcript`, `feedback {pronunciation: [{word, score}], grammar_notes[]}`, `reply {text, audio_url}` | Owner | Session open; ≤ 30 turns | 409 `session_closed` | T-ai / R |
| `POST /v1/ai/viva/sessions` | `{scenario_id}` | `{session_id, first_question_text, audio_url?}` | User (track matches the scenario) | – | 404 | T-ai / R |
| `POST /v1/ai/viva/sessions/{id}/turns` (G.3) | `{upload_id? or text?}` | SSE: `score {rubric_points[]}`, `next_question` or `final {total, feedback, label: "practice feedback"}` | Owner | Exactly one input | 409 | T-ai / R |

### D.6 Gamification

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/store/items` | – | `{coins, items: [{id, kind, cost_coins, stock?, title}]}` | User | – | – | T-read / – |
| `POST /v1/store/redemptions` | `{item_id}` + `Idempotency-Key` | `{redemption_id, status, fulfilment: {entitlement_id?|coupon_code?|ticket_id?}, coins_left}` | User | Item active; stock | 409 `insufficient_coins`, 409 `out_of_stock` | T-write / R |
| `POST /v1/follows/{user_id}` | – | `{following: true}` | User | Not self; target not opted out of boards | 404, 409 | T-write / – |
| `DELETE /v1/follows/{user_id}` | – | 204 | User | – | – | T-write / – |
| `GET /v1/team-leagues/current` | `?track_id` | `{week_key, standings: [{rank, institution_name, xp, members, label}], my_institution_rank?}` | User | – | – | T-read / – |

### D.7 Planner channels

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/channels/{channel}` | `channel ∈ {whatsapp, telegram}`; `{phone?}` (WhatsApp) | Telegram: `{deep_link}`. WhatsApp: `{verification: sent}` | User (adult, or a minor with consent scope) | – | 403 `consent_required` | T-write / O |
| `DELETE /v1/channels/{channel}` | – | 204 | User | – | – | T-write / – |
| `POST /v1/calendar-feed` | `{rotate?: bool}` | `{feed_url}` | User | – | – | T-write / – |
| `GET /v1/calendar-feed/{token}.ics` | – | `text/calendar` | Token (hashed lookup) | – | 404 | T-read / – |
| `POST /v1/webhooks/telegram` (G.2) | Telegram update | 200 | Secret-token header | Binds by deep-link token | 401 | T-webhook / – |
| `GET`/`POST /v1/webhooks/whatsapp` (G.2) | Verify challenge / message status updates | 200 | Verify token / HMAC | – | 401 | T-webhook / – |

### D.8 Community

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/forums/{category_id}/threads` | `?cursor&sort` | `Page<{thread_id, title, posts, last_post_at}>` | User | – | 404 | T-read / – |
| `POST /v1/forums/{category_id}/threads` | `{title 5–150, body 1–2,000}` | `{thread_id, moderation_status}` | User; not restricted | `moderate()` on both | 422 `moderation_blocked` | T-write / O |
| `GET /v1/study-groups` | `?mine=true&cursor` | `Page<{id, name, members, kind}>` | User | – | – | T-read / – |
| `POST /v1/study-groups` | `{name, kind: peer|institution, batch_id?}` | `{id, invite_code}` | User (institution kind needs a verified teacher of the batch) | D9-4 rules | 403 | T-write / O |
| `POST /v1/study-groups/{id}/members` | `{invite_code}` | `{group_id, role}` | User | D9-4: consent for minors; adult admission rules | 403 `minor_safety`, 403 `consent_required` | T-write / O |
| `GET /v1/study-groups/{id}/messages` | `?cursor` | `Page<{id, author_display_name, body, created_at}>` | Member | – | 404 | T-read / – |
| `POST /v1/study-groups/{id}/messages` | `{body ≤ 1,000, media_upload_id?}` | `{id}` | Member; not muted | `moderate()`; media moderated | 422 | T-write / O |

### D.9 Parents, institutions and commerce

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/guardian/children/{child_id}/alerts` | – | `{rules[], recent_events[]}` | Active link | – | 404 | T-read / – |
| `POST /v1/guardian/children/{child_id}/alerts` | `{kind: no_study_days|score_drop, threshold: {days?|drop_pct?}}` | Rule | Active link | `days` 1–14; `drop_pct` 5–50 | 422 | T-write / O |
| `DELETE /v1/guardian/children/{child_id}/alerts/{id}` | – | 204 | Active link | – | 404 | T-write / – |
| `POST /v1/workspaces/{id}/listings` / `PATCH …/{lid}` | `{kind: exam_series|notes, title, price_poisha, content_ref, revenue_share_bps (from contract)}` | `{listing_id, status: in_review}` | Role:inst.teacher; verified payout account | Price within the floor and ceiling | 403 `payout_unverified`, 422 | T-write / R |
| `GET /v1/marketplace` | `?track_id&kind&cursor` | `Page<{listing_id, title, workspace_name, price}>` | User | – | – | T-read / – |
| `GET /v1/workspaces/{id}/payout-account` | – | `{method, masked_details, verified_at}` | Role:inst.admin | – | – | T-read / – |
| `PUT /v1/workspaces/{id}/payout-account` | `{method: bkash|bank, details}` | `{status: unverified}` (re-verification on change) | Role:inst.admin (audited) | Details format | 422 | T-write / – |
| `GET /v1/workspaces/{id}/whitelabel` | – | Config | Role:inst.admin | – | – | T-read / – |
| `PUT /v1/workspaces/{id}/whitelabel` | `{subdomain, theme, enabled_features[]}` | Config `{status: pending_dns}` | Role:inst.admin and a plan that includes white-label | Reserved words; DNS label | 409 `subdomain_taken`, 403 | T-write / – |
| `GET /v1/whitelabel/{subdomain}/config` | – | `{workspace_id, name, logo_url, theme, enabled_features}` | Public | – | 404 | T-read / – |
| `POST /v1/workspaces/{id}/attendance` | `{batch_id, class_date, records: [{roster_entry_id, status: present|absent|late}]}` | `{saved}` | Role:inst.teacher (batch) | Date ≤ today; edits after 7 days need inst.admin | 422 | T-write / R |
| `GET /v1/workspaces/{id}/fees` | `?period&status&cursor` | `Page<FeeRecord>` | Role:inst.admin | – | – | T-read / – |
| `POST /v1/workspaces/{id}/fees` | `{roster_entry_id, period, amount_poisha, paid_at?, method?}` | `FeeRecord` | Role:inst.admin (audited) | `amount_poisha ≥ 0` | 422 | T-write / R |
| `POST /v1/admin/sponsorships` / `PATCH …/{id}` | `{sponsor_id, product_id, seats, valid_to, criteria}` | Sponsorship | Staff:pay.catalogue (audited) | `seats > 0` | 422 | T-admin / R |
| `POST /v1/admin/sponsorships/{id}/seats` | `{user_ids[]}` (≤ 500) | `{granted: [...], skipped: [{user_id, reason}]}` | Staff:pay.grant (audited) | Criteria match; seats left | 409 `no_seats` | T-admin / R |

---

## E. Testing strategy

| Kind | Files | Cases |
|---|---|---|
| Unit | `tests/modules/com/unit/test_group_safety.py` | Table of D9-4 cases: minor + unknown adult refused; verified teacher allowed in an institution group; linked guardian allowed; consent missing refused |
| Unit | `tests/modules/gam/unit/test_store_coins.py` | Earn rule and daily cap; redemption never touches XP; negative balance impossible |
| Unit | `tests/modules/par/unit/test_alert_rules.py` | No-study days across a Dhaka midnight; score-drop percentage |
| Unit | `tests/modules/exam/unit/test_predictor.py` | Monotonic mapping; widens with sparse data |
| Unit | `tests/modules/inst/unit/test_payout_math.py` | bps maths floors to whole poisha; refunds subtract; never negative |
| Unit | `tests/modules/inst/unit/test_subdomain_rules.py` | Reserved words, length, punycode refused |
| Integration | `tests/modules/auth/integration/test_data_deletion.py` | Full deletion: PII nulled, hashes replaced, external identities gone, files deleted (fake S3), learning rows keep the pseudonymous id; resume after a crash at each step |
| Integration | `tests/modules/auth/integration/test_data_export.py` | The export contains only the user's data; the link is single use |
| Integration | `tests/modules/auth/integration/test_consent_withdraw.py` | Minor withdrawal → restricted mode blocks AI, groups and boards; practice still works |
| Integration | `tests/modules/gam/integration/test_redemption_concurrency.py` | 20 parallel redemptions with coins for 5 → exactly 5 succeed (concurrency) |
| Integration | `tests/modules/pay/integration/test_sponsored_seats.py` | Seat pool exactness under concurrency |
| Integration | `tests/modules/prac/integration/test_duel_flow.py` | Two WS clients (HTTPX + `websockets` test client): rounds, a late answer refused, results, answers copied once to `attempt_answers` with notebook and XP rules |
| Integration | `tests/modules/prac/integration/test_realtime_scaleout.py` | Two realtime app instances on one Redis: a room spans instances; a revoked session disconnects within 60 s |
| Integration | `tests/modules/exam/integration/test_proctoring.py` | Consent required; rate limit; purge after 30 days (frozen clock) |
| Integration | `tests/modules/plan/integration/test_channels.py` | Telegram binding by deep link; WhatsApp HMAC; quiet hours respected; iCal feed includes plan items |
| Integration | `tests/modules/inst/integration/test_marketplace.py` | Listing blocked without a verified payout account; platform review needed; payout once per period |
| Integration | `tests/modules/nfr/integration/test_replica_routing.py` | Allow-listed route reads the replica; lag above the threshold falls back to the primary; a non-listed route never uses the replica |
| Integration | `tests/core/test_sqs_job_backend.py` | LocalStack: the same handler semantics as Postgres jobs; dedupe through `processed_events` |
| API | `tests/modules/*/api/test_*_b09.py` | Every endpoint in §D: success, validation, authorization, idempotent replay, flags off → 503 |
| Authorization | `tests/contract/test_cross_tenant.py` (extended) | New tenant tables (white-label, attendance, fees, listings, classroom rooms) are in the generated suite |
| AI eval | `tests/eval/test_voice_gates.py` (marker `eval`) | STT WER at or below the gate; spoken-English feedback agreement with teacher ratings ≥ threshold; viva rubric scoring agreement ≥ threshold; safety set 99% handled |
| Compatibility (OFF-05) | `tests/contract/test_desktop_exam_compat.py` | A desktop user agent and viewport flow through registration, start, ingest batches, key fetch, submit and result use only existing endpoints, and get identical responses to mobile. No backend change is needed. |
| Regression | B1–B8 suites | Unchanged, and green with `JOB_BACKEND=postgres` |
| Load: learners | `tests/load/learner/*.js` | Stages 1k → 100k against `perf` (§F.1 criteria) |
| Load: exam | `tests/load/exam/` | 250k rehearsal with fault injection (§F.1 criteria) |
| Throughput | `tests/load/relay_throughput.py`, `tests/load/jobqueue_throughput.py` | Measured events per second per shard; jobs per second and claim latency at 250, 500, 1,000 and 2,000 |
| Failure | `tests/load/chaos/*.md` runbooks | Primary failover during the 10k stage; Redis restart (boards rebuilt; quotas reset is safe); AI provider outage (graceful `unavailable` within 2 s) |

**Coverage:** ≥ 85% overall. ≥ 95% on:
- `auth/internal/services/{data_deletion,data_export,consent_dashboard}.py`
- `gam/internal/services/{store,coins}.py`
- `com/internal/services/group_safety.py`
- `inst/internal/services/payouts.py`
- `pay/internal/services/sponsorships.py`
- `prac/internal/realtime/rounds.py`
- `core/db_replica.py`

---

## F. Build completion

### F.1 Acceptance criteria

**Features**

1. All 20 P2 IDs are demonstrated by API tests mapped in the traceability matrix. The total is now 180 of 180.
2. A voice feature with a failed gate stays disabled, and the build report records which gates passed.
3. Deletion is proven end to end on a seeded account, and no PII remains (a scripted scan of all `*_enc` and `*_hash` columns for that user).
4. The minor-safety suite (D9-4) passes 100%.

**Scale certification.** These are proposed pass criteria; `17` holds the authoritative numbers, and if the two differ, `17` wins. Each stage is held for 30 minutes at the stated concurrency, on the workload model.

| Stage | Pass |
|---|---|
| 1k, 10k | API p95 < 300 ms, p99 < 800 ms; answer-save p95 < 250 ms; error rate < 0.1%; DB CPU < 60% |
| 50k | Same latency targets; error rate < 0.2%; leaderboard and notification lag p95 < 5 s; outbox lag p95 < 30 s |
| 100k | API p95 < 400 ms on the answer and read paths; error rate < 0.5%; AI admission control keeps provider calls within the configured concurrency, with excess requests getting a clean `unavailable` or queued status (no 5xx storms); DB CPU < 75%; no PgBouncer wait-queue growth |
| Exam 250k rehearsal | Every acknowledged answer scored; the contiguity check finds every injected gap; merit identical across 3 replays; batch acknowledgement p95 < 2 s; provisional score p95 < 5 s after end; result-read rush served from Redis with zero DB queries |

If a stage fails, the build report records the bottleneck and the change made. A stage is either re-run to a pass, or the supervisor accepts the measured limit as the supported stage. **No capacity is claimed beyond the highest passing stage.**

### F.2 Deliverables

- Migrations `b09_01`–`b09_13`; module code per §C.3; the `realtime` deployable (Dockerfile target, ECS service definition in infrastructure code); provider adapters (speech, Telegram, WhatsApp).
- Load scenarios and harnesses; `docs/capacity/` reports per stage.
- Updated autoscaling and pool configuration.
- Runbooks: realtime incidents, data deletion, voice provider outage, replica lag.
- Updated OpenAPI snapshot and the final build report.

### F.3 Definition of done

Per [`21`](21_definition_of_done.md), plus:
- The capacity reports are reviewed by the SRE lead.
- Privacy sign-off on AUTH-10, EXAM-14, COM-04 and AI-12–14 data handling is recorded (pending D4).
- The traceability check reports 180/180 with a passing test reference for each ID.

### F.4 Manual verification checklist

- [ ] A guardian withdraws consent for a 15-year-old; the child's AI and boards are blocked and practice still works.
- [ ] Request deletion, cancel within the grace period; request again and let it run; the account is anonymised and the user cannot sign in.
- [ ] Play a duel between two browsers on two realtime instances; check the notebook and XP afterwards.
- [ ] Redeem coins for AI credits; the quota rises; XP and level are unchanged.
- [ ] Create a peer group as a 14-year-old; an unknown adult's join is refused.
- [ ] Bind Telegram; receive a streak reminder outside quiet hours only.
- [ ] Create a marketplace listing; it is refused until the payout account is verified.
- [ ] Open the white-label config for a test subdomain.
- [ ] Review the 100k-stage report: bottleneck named, next trigger written.
- [ ] Review the 250k rehearsal report: zero acknowledged answers lost.

### F.5 Exit criteria: end of the backend programme

F.1–F.4 are done. All nine builds are merged. The traceability matrix shows 180/180. The supervisor approves the capacity statement (the highest passing stage) and the start of the frontend phase.

---

## G. Proposed additions (accepted)

All items were **accepted** during integration and are now in [`01`](01_database_design.md) §3 and §4.E and in [`14`](14_api_contracts.md). The `family_plan` and `reward_store` entitlement sources are the final names.

| # | Addition | Why | Change |
|---|---|---|---|
| G.1 | Endpoints `GET /v1/me/consents`, `POST /v1/me/consents/{id}:withdraw` and `DELETE /v1/me/data-requests/{id}` | AUTH-10 needs a consent dashboard and a cancellable deletion grace period | `14` §3.2 (B9) |
| G.2 | Endpoints `POST /v1/webhooks/telegram`, and `GET`/`POST /v1/webhooks/whatsapp` | PLAN-07 binding and delivery status need inbound webhooks | `14` §3.12 (B9) |
| G.3 | Table `ai.voice_turns` (PK `(session_id, turn_no)`; `input_audio_key`, `transcript`, `feedback jsonb`, `reply_text`, `reply_audio_key`, `scores jsonb`, `created_at`). Endpoints `POST /v1/ai/spoken-english/sessions/{id}/turns` and `POST /v1/ai/viva/sessions/{id}/turns`. | AI-13 and AI-14 are multi-turn; `14` has only session creation | `01` §3.12 and `14` §3.8 (B9) |
| G.4 | `practice.attempt_answers.context` value `duel` | PRAC-13 answers feed the normal learning records | `01` §4 practice spec |
| G.5 | `commerce.entitlements.source` values `reward_store` and `scholarship` (confirm that `scholarship` is in the B3 check) | GAM-08 AI-credit fulfilment and PAY-08 | `01` §4 commerce spec |
| G.6 | Quota features `voice_minutes_per_day`, `spoken_english_minutes_per_day` and `viva_sessions_per_week` | Cost control for the voice features (AI-15 rule applied) | `01` §4 commerce spec |
| G.7 | Column `exam.exams.settings jsonb DEFAULT '{}'` (holds `proctoring_required`, `shuffle`, `sets`), or a set of explicit columns | EXAM-14 and the B8 shuffle options need per-exam settings; `01` lists no settings column | `01` §3.10 (prefer one jsonb validated by a pydantic model) |
| G.8 | `commerce.products.kind` value `notes` | INST-09 notes listings | `01` §4 commerce spec |

**Inconsistencies noted:**
- `14` §3.2 marks `GET /v1/me/data-export/{id}` as B9 while `POST /v1/me/data-requests` is B6. The B6 support-driven path delivers exports by staff hand-off; this build adds the self-service download, which is consistent with that split.
- `01` §3.3 lists `community.threads.scope` with "forum topics in 9", which this build uses.

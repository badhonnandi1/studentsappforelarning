# 12 · Build 8: P1 institutions, parents, exam integrity and growth

**Build:** 8 of 9 · **Priority band:** P1, plus the deferred parts of AUTH-01 · **Date:** 2026-11-27
**Depends on:** Builds 1–7 merged and green. Build 7 supplies QB-10 families, used by EXAM-09, and the `par.tutor_mode_lock` contract.
**Unblocks:** Build 9
**Read first:** [`04_backend_master_plan.md`](04_backend_master_plan.md), [`01_database_design.md`](01_database_design.md) §1.1, §3 and §5, [`14_api_contracts.md`](14_api_contracts.md) §1–§3, [`18_security_architecture.md`](18_security_architecture.md) (tenant isolation, PII), [`15`](15_testing_and_quality_standards.md), [`21`](21_definition_of_done.md)

---

## 0. How to run this build (coding-agent preamble)

1. Read the documents above. In `14`, every row with **B = 8** is in scope. In `01`, read the rows marked B 8, and §1 *Tenancy*.
2. Confirm Build 7 is complete:
   - `scripts/check.sh` passes on `main`.
   - `alembic current` is at the `b07_*` head.
   - `qb.family_of()` and `par.tutor_mode_lock()` exist.
3. Create the branch `build/08-institutions-parents-integrity`.
4. **Tenant isolation is the first step and the gate for everything else** (§C.1 steps 1–3). No institution feature merges before the cross-tenant test suite passes.
5. Follow §C in order, writing tests alongside the code. Run `scripts/check.sh` after every step.
6. Before any live integration, external-provider facts marked **[Needs evidence]** must be checked against current provider documentation. These are bKash recurring payments, Apple guideline 4.8, and the email and SMS vendors. Record what you find in the PR.
7. Verify §F. **Stop.** Do not start Build 9 and do not touch the frontend.

---

## A. Overview

| Item | Value |
|---|---|
| Name | P1 institutions, parents, exam integrity and growth |
| Objective | Open the B2B channel (coaching centres and schools), the parent portal, exam anti-cheat, written exams and series, and the growth tooling. Also ship the iOS backend and the remaining sign-in methods. |
| Business value | Institution licences and seat revenue, parent trust and payment (PAR-04), certificates and series as products, campaigns and A/B tests |
| Technical value | Turns `tenant_id` from a column into enforced row-level security across data, search, embeddings and caches; proves the platform can host private content safely |
| Complexity | 5 / 5. Tenant isolation and the leak paths around it (search, AI retrieval, caches, statistics) are the highest-risk work after the exam engine. |
| Effort | 15–21 backend person-weeks **[Assumption]** |
| Modules | INST, AUTH, PAR, EXAM, PLAN, PAY, OPS, QB, AI and NFR (isolation hooks), ANL (read interfaces) |

### A.1 Features

| ID | Feature in this build |
|---|---|
| INST-01 | Institution workspace with logo and branding, branches, teachers, and batches or sections (extends the B6 batches) |
| INST-02 | Student roster management (invite, CSV, roll number); seat and licence allocation as entitlements with source `institution_seat` |
| INST-03 | Exams built from the platform bank and/or the institution's private bank. Private questions never leave the tenant. |
| INST-04 | Batch exam scheduling online, with results and a merit list within the batch |
| INST-05 | Mobile OMR: a printable OMR sheet generator; the phone scan posts detected bubbles, which are auto-graded and synced to student accounts |
| INST-06 | Question paper generator: print-ready PDF with Bangla typesetting, sets A/B/C/D, answer key, institution header |
| INST-07 | Analytics per batch and per student: weak chapters, participation, comparison between batches |
| INST-08 | Homework with due dates; written submissions; AI-assisted grading (the B6 pipeline) with teacher override |
| AUTH-07 | Parent–child linking by invite code or QR; one parent can have many children |
| AUTH-08 | Several student profiles on one shared device, each unlocked by a local PIN (the server stores only the device–account links) |
| AUTH-09 | Institution enrolment via join code, CSV upload or roll-number import |
| AUTH-01 (deferred part) | Email and password sign-in, plus **Sign in with Apple** (user-approved scope, 2026-11-27) |
| PAR-01 | Child overview: study time, streak, exams taken, scores, rank trend, weak subjects |
| PAR-02 | Weekly report in the app and by Bangla SMS |
| PAR-03 | Controls: tutor mode lock, daily time cap, quiet hours, all enforced on the server |
| PAR-04 | Pay for a child's subscription; family plan |
| EXAM-09 | Paper-side anti-cheat: question and option shuffle, per-user variants from QB-10 families, per-user sets, single device |
| EXAM-09a | Device-side anti-cheat: app-switch and tab-blur logs, screenshot-attempt logs (`FLAG_SECURE` is on the client) |
| EXAM-09b | Analysis-side anti-cheat: IP and device anomaly flags, answer-similarity collusion detection, an admin review console |
| EXAM-10 | Written exam submission: photos or PDF per question, graded by AI drafts and/or a human examiner using a rubric |
| EXAM-11 | Exam series and packages with a schedule and a cumulative leaderboard |
| EXAM-12 | Certificates (PDF with a verification QR) for live-exam toppers and series completion |
| PLAN-04 | Circular and exam-date tracker: application windows, admit cards, exam dates, results |
| PLAN-04a | Follow-and-alert on tracker items; admins manage the data |
| PLAN-05 | Eligibility checker: a rules engine over GPA, year, group, age and subject |
| PLAN-06 | Bangla SMS channel for critical alerts |
| PAY-06 | Auto-renew subscriptions where the gateway supports tokenisation; family plan; bundles; upgrade or downgrade with proration |
| PAY-07 | Affiliate and campus-ambassador programme with tracking links and payout reports |
| OPS-05 | Campaign tools: segmented push, SMS and email; A/B testing |
| OPS-06 | Business analytics: DAU and WAU, funnels, conversion, retention, revenue, AI cost per user (from the S3 log) |
| OPS-07 | Feature flags and remote config, extending the B1 kill switches |
| OFF-04 (backend) | APNs push, Apple IAP verification, App Store Server Notifications v2, Sign in with Apple and token revocation |
| NFR-11 (backend) | Alt text required on published images, accessible labels in payloads, font-scaling-safe rendered HTML |

**Total: 32 P1 IDs, plus the deferred parts of AUTH-01.**

### A.2 Dependencies

| Needs | From |
|---|---|
| `tenant_id` columns and tenant filters in queries | B2 onwards |
| Batches, written tasks, submissions, gradings, teacher queue | B6 |
| Exam engine, blueprints, scoring, merit, papers, ingest | B5 |
| QB-10 families; `par.tutor_mode_lock` contract | B7 |
| Orders, payments, Play Billing, webhooks, entitlements, referrals | B3, B6 |
| Social provider interface and `external_identities` | B1 |
| PDF rendering with Bangla fonts (invoices and compilations) | B6, B7 |
| DuckDB warehouse runner | B7 |

### A.3 Risks and blockers

| Risk | Mitigation |
|---|---|
| A cross-tenant leak through a path that bypasses RLS: Redis caches, search, embeddings, item statistics, canonical cache, S3 keys | RLS is defence in depth, not the only control. Every cache key and index filter includes the tenant scope. A generated cross-tenant test runs against every endpoint, plus search and retrieval. Private content is excluded from statistics jobs and from the canonical cache by construction (§C.3). |
| RLS with PgBouncer transaction mode | Use only `SET LOCAL` inside the transaction. Never use session `SET`. A test asserts that no `app.*` setting survives a connection return. |
| RLS slows hot queries | Policies are simple equality or `= ANY` on an indexed `tenant_id`. `EXPLAIN` checks in tests on the answer path and session start. The answer path touches only tables without tenant policies, or with `tenant_id IS NULL` fast-path indexes. |
| bKash tokenised recurring payment eligibility **[Needs evidence]** | Subscriptions engine with per-provider capability flags. Where tokenisation is unavailable, renewal becomes a reminder plus a one-tap order. |
| Apple guideline 4.8 wording, revocation API details **[Needs evidence]** | Verify before the iOS submission. Apple sign-in is behind a feature flag. |
| No email transport exists before this build | Proposed addition G.3 adds an email adapter in PLAN (SES or a local vendor), used by password reset and OPS-05 |
| Collusion detection false positives on minors | Flags only. A human decides. A flag never changes a result automatically, and every decision is audited. |

---

## B. Database implementation

### B.1 Tables to create

These come from `01` §3; full specifications are in `01` §4.

| Schema.table | Feature |
|---|---|
| `institution.workspaces`, `branches`, `workspace_members` | INST-01 |
| `institution.roster_entries`, `roster_imports`, `seat_allocations` | INST-02, AUTH-09 |
| `institution.homework_assignments` | INST-08 |
| `institution.omr_templates`, `omr_scans` | INST-05 |
| `institution.paper_generations` | INST-06 |
| `parent.guardian_links`, `link_codes`, `parent_controls`, `weekly_reports` | AUTH-07, PAR-01–03 |
| `identity.device_profile_links` | AUTH-08 |
| `identity.password_credentials`, `email_verifications`, `apple_notifications` | AUTH-01 |
| `exam.integrity_events` P, `anomaly_flags` | EXAM-09a, EXAM-09b |
| `exam.attempt_question_orders`, `paper_set_assignments` | EXAM-09 |
| `exam.written_answers`, `written_answer_pages` | EXAM-10 |
| `exam.series`, `series_items`, `series_standings`, `certificates` | EXAM-11, EXAM-12 |
| `notify.tracker_items`, `tracker_follows`, `eligibility_targets`, `eligibility_rules` | PLAN-04, PLAN-04a, PLAN-05 |
| `commerce.subscriptions`, `family_plans`, `family_members`, `proration_quotes`, `bundles` | PAY-06, PAR-04 |
| `commerce.affiliates`, `affiliate_attributions`, `affiliate_payouts` | PAY-07 |
| `ops.feature_flags`, `campaigns`, `campaign_sends` P, `experiments`, `experiment_assignments` | OPS-05, OPS-07 |
| `notify.email_messages` P | **Proposed** (G.3) |

### B.2 Tables to modify

| Table | Change | Kind |
|---|---|---|
| `institution.batches` | Populate `workspace_id` (nullable FK to `workspaces`); `kind` gains `section` | Expand |
| `commerce.entitlements` | Populate `beneficiary_user_id`; `source` check gains `institution_seat` (if not already present) and `family_plan` (G.5) | Expand |
| `commerce.orders` | Populate `beneficiary_user_id` | Expand (column exists) |
| `commerce.store_purchases` | `platform` check gains `apple` | Expand |
| `notify.push_tokens` | `platform` check gains `apns` | Expand |
| `identity.external_identities` | `provider` check gains `apple`; add `provider_refresh_token_enc bytea NULL` (Apple only, G.2) | Expand |
| `qbank.question_versions`, `qbank.qv_content` | Add `tenant_id uuid NULL`, back-filled from `questions.tenant_id` (G.1) | Expand → backfill → `NOT NULL`-free (nullable means platform) |
| Tenant-scoped tables (list in §B.4) | `ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + policy | Staged contract (§B.3) |
| `qbank.question_media` | Policy: an image cannot be published without `alt_text_bn` or `alt_text_en` (enforced in the CMS publish service, configurable) | Service rule |

### B.3 Migration sequence

Each step is a separate revision of no more than 200 lines. Partition and RLS helpers come from `migrations/helpers/`.

| # | Revision | Content |
|---|---|---|
| 1 | `b08_01_qbank_version_tenant_cols` | Add `tenant_id` to `question_versions` and `qv_content`; indexes `(tenant_id) WHERE tenant_id IS NOT NULL` |
| 2 | `b08_02_qbank_version_tenant_backfill` | Batched backfill in 10,000-row chunks (data migration, idempotent) |
| 3 | `b08_03_rls_roles_and_settings` | Create roles `app_api` and `app_worker` (if not present) and `app_breakglass` (NOLOGIN, used through `SET ROLE` only by the audited service); helper functions `app_tenant_ids()` and `app_break_glass()` (`STABLE`, read `current_setting(..., true)`) |
| 4 | `b08_04_rls_policies_content` | Policies, not yet enabled, on `qbank.questions`, `question_versions`, `qv_content`, `papers`, `concept_notes`, `flashcard_decks`, `platform.search_documents`, `ai.content_chunks` |
| 5 | `b08_05_rls_policies_exam_inst` | Policies on `exam.exams`, `exam_papers`, `exam_audiences`, and on `institution.*` tables that carry `tenant_id` |
| 6 | `b08_06_institution_workspaces` | Workspaces, branches, members; `batches.workspace_id` FK `NOT VALID` |
| 7 | `b08_07_institution_roster_seats` | Roster entries and imports, seat allocations |
| 8 | `b08_08_institution_omr_papers_homework` | OMR templates and scans, paper generations, homework |
| 9 | `b08_09_parent` | Guardian links, link codes, controls, weekly reports |
| 10 | `b08_10_identity_p1` | Device profile links, password credentials, email verifications, Apple notifications, `external_identities` changes |
| 11 | `b08_11_exam_integrity` | Integrity events (partitioned, monthly), anomaly flags, question orders, set assignments |
| 12 | `b08_12_exam_written_series_certs` | Written answers and pages, series, items, standings, certificates |
| 13 | `b08_13_notify_tracker_eligibility_email` | Tracker, follows, eligibility targets and rules, email messages (partitioned, G.3) |
| 14 | `b08_14_commerce_subscriptions_family` | Subscriptions, family plans and members, proration quotes, bundles, check widenings |
| 15 | `b08_15_commerce_affiliates` | Affiliates, attributions, payouts |
| 16 | `b08_16_ops_flags_campaigns` | Feature flags, campaigns, campaign sends (partitioned), experiments, assignments |
| 17 | `b08_17_rls_enable_content` | `ENABLE` and `FORCE` RLS on the content group. Runs **only after** the code that sets `SET LOCAL app.tenant_ids` on every path is deployed. Downgrade disables. |
| 18 | `b08_18_rls_enable_exam_inst` | Same for the exam and institution group |

**Expand/contract order for RLS:**
1. Deploy code that always sets the tenant context (steps 1–16 plus §C.1 steps 1–3).
2. Run the cross-tenant suite against staging with RLS still disabled. This proves that the application filters work.
3. Apply migration 17, then 18, one group at a time, watching for errors and the latency dashboards.
4. Rollback is a downgrade migration that disables RLS; it does not touch application code.

### B.4 Row-level security design

```sql
-- applied by helpers/rls.py for each tenant table
ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <t> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_read ON <t> FOR SELECT
  USING (tenant_id IS NULL OR tenant_id = ANY (app_tenant_ids()) OR app_break_glass());
CREATE POLICY tenant_write ON <t> FOR INSERT, UPDATE, DELETE   -- one policy per command in practice
  USING (tenant_id = ANY (app_tenant_ids()) OR (tenant_id IS NULL AND app_platform_writer()))
  WITH CHECK (tenant_id = ANY (app_tenant_ids()) OR (tenant_id IS NULL AND app_platform_writer()));
```

| Setting (all `SET LOCAL`) | Set by | Value |
|---|---|---|
| `app.tenant_ids` | `core.db.tenant_context(session, actor)` at the start of every transaction that touches tenant tables | The actor's tenants: active `workspace_members`, the tenant ids of the actor's active `batch_members`, and roster-linked workspaces. Empty for plain learners, who therefore see only `tenant_id IS NULL` rows plus their own tenants. |
| `app.platform_writer` | The CMS and QB services for staff with platform content permissions | `on` / unset |
| `app.break_glass` | `ops.break_glass(session, actor, reason)`. It writes an `ops.audit_log` row first in the same transaction and requires the permission `platform.break_glass`. | `on` / unset |

**Workers:**
- Jobs that operate on tenant data carry `tenant_id` in the payload and set it.
- Platform-wide jobs (item statistics, search reindex of platform content, trends) set nothing, so they see only platform rows. This is the structural guarantee that private questions never enter statistics or the canonical cache.
- The tenant-aware search reindex job runs once per tenant.

**Non-Postgres stores:**

| Store | Rule |
|---|---|
| Redis | Every key family holding content includes a tenant segment: `qv:{tenant\|pub}:{qv_id}`, `search:{tenant_scope_hash}:…`. The canonical cache is platform-only (`tenant_id IS NULL` versions only). |
| `search_documents` and `content_chunks` | Policies above, plus explicit `tenant_id` filters in the query builders. Similar-question and photo-match queries add `AND tenant_id IS NULL OR tenant_id = :caller_tenant`. Private items from *another* tenant are excluded even when the caller is a member of several tenants, unless the session's context is that tenant. |
| S3 and R2 | Private media keys prefixed `t/{tenant_id}/…`. Signed URLs are issued only after an RLS-checked read of the owning row. |

### B.5 Transaction and integrity requirements

| Operation | Requirement |
|---|---|
| Seat allocation on roster claim | In one transaction: `UPDATE seat_allocations SET seats_used = seats_used + 1 WHERE id=:id AND seats_used < seats_total RETURNING`, then the entitlement insert (`source='institution_seat'`, `source_ref=roster_entry_id`) and `roster_entries.user_id`. Concurrency race R18 (`01` §5.2). |
| Guardian link | Code redeem: `link_codes.used_at IS NULL AND expires_at > now()` under `FOR UPDATE`, then the `guardian_links` insert (partial unique on the active pair), audited as a security event. |
| Parent control change | Upsert `parent_controls`, outbox `parent.controls_changed`. AI and PLAN invalidate their caches on the event within 30 s. |
| OMR scan grading | The scan row is stored first. Grading posts answers through the EXAM non-live attempt API (`/v1/exam-attempts/{id}/answers` service function), so scoring, mastery and notebook follow the normal path. Idempotent on `(exam_id, roster_entry_id)`. |
| Series standings | Recomputed from `exam_results` (final phase) of the series' exams by a job; keyed by PK; never written by the exam path |
| Certificate issue | `verify_code` is 12 base32 characters from a CSPRNG (unique). PDF generated after commit. Revocation sets `revoked_at`, and the verify endpoint then shows "revoked". |
| Subscription renewal | A scheduled job creates an order with `Idempotency-Key = sub:{id}:{period_end}`, so each renewal period gets exactly one order |
| Family plan | Member add: under the plan row lock, count active members `< max_members`, then insert the member and an entitlement (`source='family_plan'`, `beneficiary_user_id` = child) |
| Affiliate attribution | `affiliate_attributions.order_id` unique. Attribution happens in the payment-capture consumer (async, idempotent), never in the capture transaction. |
| Campaign send | Each recipient is processed through `campaign_sends` PK `(campaign_id, user_id, created_on)`. Respects quiet hours and minors' rules (no promotional push to minors 22:00–07:00; SMS campaigns to minors need guardian consent scope). |
| Feature flag evaluation | Pure function over `(flag, actor attributes)`. Flags are cached for 30 s and invalidated by an outbox event. |

---

## C. Backend implementation

### C.1 Steps in dependency order

1. **Tenant context plumbing (NFR, core):**
   - `core/db_tenant.py` provides `tenant_context()`, and `auth.tenant_ids_for(actor)` is cached for 60 s per session.
   - Every service that touches tenant tables opens its transaction with `async with tenant_tx(session, actor):`.
   - A lint check, `scripts/check_tenant_tx.py`, greps the repositories that touch tenant tables and fails if a service calls them outside `tenant_tx`.
2. **Version tenant columns and backfill** (migrations 1–2). QB writes `tenant_id` on every new version.
3. **RLS policies (not enabled), the break-glass service and the cross-tenant test generator** (§E). Run the suite with application filters only; it must pass before step 4.
4. **INST-01 workspaces:** CRUD, branding (logo upload through presigned URL, moderated), branches, members. The B6 batches are attached to workspaces.
5. **AUTH-09 and INST-02 rosters:** CSV import (job, row report), roll-number entries, invites, the claim flow, seat allocations as entitlements.
6. **INST-03 private bank:** the B2 QB and CMS flows with `tenant_id`. The workflow for private content needs one verifier from the same workspace with the `content.verify` grant in tenant scope; the two-person rule still applies. Private items are excluded from platform search, similar questions, item statistics and the canonical cache. **Tenant vector search (R-23):**
   - Filtered HNSW loses recall, so tenant-private retrieval uses pgvector ≥ 0.8 with `hnsw.iterative_scan = relaxed_order` and a tuned `hnsw.ef_search` (default 100, raised for filtered queries).
   - A workspace with ≥ 20,000 private chunks or questions gets a **partial HNSW index** `WHERE tenant_id = '<id>'`, created concurrently by a job when the threshold is crossed.
   - Smaller tenants use **exact search** (sequential scan over the tenant's rows under RLS), which is fast at that size.
   - The search gate adds tenant-filtered queries.
7. **INST-04 batch exams and merit** (EXAM with `tenant_id`, audience = batch), plus **INST-07 analytics** (ANL read interface, batch-filtered).
8. **INST-05 OMR:** template PDF generator (reportlab with the Bangla font; layout encodes question count and roll-number grid), and scan intake that validates detected bubbles, grades through EXAM and links to the roster.
9. **INST-06 paper generator:** sets A–D by shuffle (EXAM-09 shuffle function reused), Bangla typesetting from `rendered_html` via WeasyPrint in the worker image, answer-key PDF.
10. **INST-08 homework:** `homework_assignments` of kind practice (creates sessions) or written (links a B6 written task), with due dates, reminders and a teacher override on AI drafts (B6 queue).
11. **AUTH-07 and PAR-01–03:**
    - Link codes and QR; links.
    - Overview from the ANL, GAM and EXAM public reads.
    - Controls.
    - `par.tutor_mode_lock` implementation (replaces the B7 `None`).
    - Time cap enforced in PRAC session start and AI gateway admission (`par.time_remaining_today(child)`).
    - Quiet hours in PLAN delivery.
12. **PAR-02 weekly report:** Saturday job builds the payload, writes the inbox, and sends a Bangla SMS through the PLAN-06 channel. Cost-capped by config.
13. **PLAN-06 SMS channel for critical alerts:** a category allow-list (exam reminders T−1 h, result published, payment failed, guardian weekly report) and a per-user daily SMS cap.
14. **PLAN-04, PLAN-04a, PLAN-05:** tracker CRUD (admin, audited), follows, alerts on change (consumer → notifications), eligibility rules engine (JSON rules: comparisons over GPA, year, group, age and subject, with `all`/`any`), and a check endpoint.
15. **EXAM-09 anti-cheat (paper side):**
    - At freeze: generate sets A–D per language. Per-user set assignment is `hash(user_id, exam_id) mod sets`, stored in `paper_set_assignments`.
    - Per-attempt shuffle seed in `attempt_question_orders`, delivered in the attempt start response. The client renders the shuffled order, and responses use canonical option labels.
    - Variant substitution within a QB-10 family at freeze time, recorded in `variant_map`.
    - Single device: the existing epoch.
    - The scorer reads `variant_map` for the per-user key.
16. **EXAM-09a:** the integrity events endpoint (batched, 50 events per call max), stored and counted. Shown in the control room.
17. **EXAM-09b:** batch jobs over the S3 log and `exam_answers_latest`:
    - Same-IP and same-device clusters.
    - Answer-similarity score (shared rare wrong answers, Jaccard over wrong options, timing correlation).
    - `anomaly_flags` with evidence.
    - Admin console list and decide, audited. A decision can invalidate an attempt only through the existing invalidate and rescore path, with ops approval.
18. **EXAM-10 written exams:**
    - Page upload per question.
    - Drafting through the B6 marking pipeline. EXAM calls `ai.request_marking(MarkingRequest)` with `submission_ref_type='exam_written_answer'` and reads drafts with `ai.get_drafts`; AI never calls EXAM or INST (R-03).
    - Human examiner queue and marks (G.4 endpoints).
    - Marks enter `exam_results` as written-section marks with the scoring source recorded. Written marks are excluded from national merit unless the exam is configured as institution-internal (v2 §4.10).
19. **EXAM-11 series and EXAM-12 certificates:** series as a product kind `exam_series`, standings job, certificates (topper rules per series or exam config: top N or top P%), verify endpoint.
20. **OFF-04 and the AUTH-01 additions:**
    - **APNs adapter:** token-based `.p8`, HTTP/2 via HTTPX.
    - **Apple IAP:** App Store Server API transaction verification (JWS) into the B6 capture transaction, and the App Store Server Notifications v2 webhook.
    - **Sign in with Apple:** a provider adapter that verifies the identity token (JWKS) and nonce, exchanges the authorization code for a refresh token (stored encrypted, G.2), and handles the Apple notifications webhook (consent revoked, account deleted). On account deletion the token is revoked.
    - **Email and password:** argon2id via `pwdlib`, 10 failed attempts → 15-minute lock, email verification, reset through the email transport (G.3), and the breached-password check (k-anonymity range API, optional by config).
21. **AUTH-08 shared device:** `device_profile_links`; each account keeps its own device session. The server never stores the PIN (it is a local unlock).
22. **PAY-06:** subscriptions engine (provider capability flags, a renewal scheduler, failure dunning with 3 tries, cancel at period end), bundles (a product granting several products), proration quotes (remaining value pro rata by days, credited to the new order), family plan.
23. **PAR-04:** pay for a child. The order's `beneficiary_user_id` must be a linked child; the entitlement goes to the beneficiary.
24. **PAY-07 affiliates:** application, tracking links (`?ref=` resolved at sign-up and order), attribution consumer, monthly payout reports (audited).
25. **OPS-07 feature flags:** targeting rules (percentage rollout by hashed user id, track, district, app version, platform), served through `/v1/config/client`.
26. **OPS-05 campaigns and A/B:** segment builder (DSL over profile, enrolment, plan and activity fields), scheduled sends through PLAN channels, sticky experiment assignments, a stats rollup job.
27. **OPS-06 BI:** saved DuckDB queries per report over the S3 log, cached for 1 h, staff only.
28. **NFR-11 backend:**
    - The publish gate requires alt text for images (config `cms.require_alt_text`, default on).
    - Payloads include `alt` and `aria_label` for option media.
    - Rendered HTML uses relative units, with no fixed font sizes, so client font scaling works.

### C.2 Design decisions

| # | Decision | Rationale |
|---|---|---|
| D8-1 | RLS is defence in depth. The application tenant filters stay mandatory. | One control can fail. Cross-tenant tests run with RLS both off and on. |
| D8-2 | `tenant_id` is denormalised onto `question_versions` and `qv_content` (G.1) | RLS needs a local column; versions are immutable, so the copy cannot drift |
| D8-3 | Break glass is a role switch inside an audited transaction, not a `BYPASSRLS` login | No standing bypass credential exists; every use is traceable |
| D8-4 | OMR images are processed on the device; the server validates the detected-bubble grid and confidence. A low-confidence scan goes to teacher confirmation. | Matches v2 §8.4 ("on-device scan posts answers through the normal attempt API"); avoids server CV infrastructure |
| D8-5 | Shuffle uses canonical labels in responses | Ingest and consumers stay unchanged; the scorer stays a pure function of `(response, key, variant_map)` |
| D8-6 | Apple refresh tokens are the only provider tokens stored (encrypted) | Apple's account-deletion revocation needs one. This is an explicit exception to the B1 rule "provider tokens never stored". |
| D8-7 | The parent daily time cap is enforced at session start and at AI admission, not mid-session | Avoids losing a student's answers mid-session; the cap check uses `analytics.daily_study` |

### C.3 Files to create or modify

Paths are relative to `backend/src/app/`. Every file is ≤ 200 lines.

**Core and tenant isolation**

| Path | Responsibility | ~Lines |
|---|---|---|
| `core/db_tenant.py` | `tenant_tx()`, `SET LOCAL` helpers, platform-writer flag | 90 |
| `modules/ops/internal/services/break_glass.py` | Audited break-glass | 70 |
| `modules/auth/internal/services/tenants.py` | `tenant_ids_for(actor)` from workspace, batch and roster membership (cached) | 90 |
| `migrations/helpers/rls.py` | Policy create, enable and disable helpers | 110 |
| `scripts/check_tenant_tx.py` | Static check that tenant repositories run inside `tenant_tx` | 100 |
| `modules/qb/internal/services/tenant_scope.py` | Version `tenant_id` propagation; private-content rules | 80 |

**Institution (INST)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/inst/internal/models/workspaces.py` | Workspaces, branches, members | 80 |
| `modules/inst/internal/models/roster.py` | Roster entries and imports, seats | 80 |
| `modules/inst/internal/models/omr_papers.py` | OMR templates and scans, paper generations | 80 |
| `modules/inst/internal/models/homework.py` | Homework | 40 |
| `modules/inst/internal/repositories/workspaces.py` | CRUD and membership | 110 |
| `modules/inst/internal/repositories/roster.py` | Entries, imports, claim, seat conditional update | 130 |
| `modules/inst/internal/repositories/omr_papers.py` | OMR and paper generation rows | 90 |
| `modules/inst/internal/repositories/homework.py` | Homework queries | 70 |
| `modules/inst/internal/services/workspaces.py` | Workspace, branding, branches, members (audited) | 150 |
| `modules/inst/internal/services/roster_import.py` | CSV parse and validation report (job) | 140 |
| `modules/inst/internal/services/roster_claim.py` | Claim by code; seat allocation; entitlement through PAY | 120 |
| `modules/inst/internal/services/private_bank.py` | Tenant-scoped authoring through the QB and CMS interfaces | 120 |
| `modules/inst/internal/services/batch_exams.py` | Batch exam creation through EXAM; merit within batch | 130 |
| `modules/inst/internal/services/omr.py` | Template generation enqueue; scan validation; grading through EXAM | 150 |
| `modules/inst/internal/services/paper_generation.py` | Sets, shuffle, PDF enqueue | 120 |
| `modules/inst/internal/services/homework.py` | Practice or written homework, reminders | 120 |
| `modules/inst/internal/services/analytics.py` | Batch and student analytics via the ANL interface | 110 |
| `modules/inst/internal/jobs/omr_template_pdf.py`, `paper_pdf.py` | PDF jobs (WeasyPrint, Bangla font) | 120 each |
| `modules/inst/internal/routes/workspaces.py` | Workspace routes | 120 |
| `modules/inst/internal/routes/roster.py` | Roster, invites, seats, claim | 110 |
| `modules/inst/internal/routes/content_exams.py` | Private questions, exams, merit | 110 |
| `modules/inst/internal/routes/omr_papers.py` | OMR and paper generations | 80 |
| `modules/inst/internal/routes/homework_analytics.py` | Homework and analytics | 90 |
| `modules/inst/internal/schemas/workspaces.py`, `roster.py`, `teaching.py` | Schemas | 100–150 each |

**Parent (PAR)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/par/internal/models/parent.py` | Links, codes, controls, weekly reports | 90 |
| `modules/par/internal/repositories/links.py` | Links and codes | 90 |
| `modules/par/internal/repositories/controls.py` | Controls, weekly reports | 70 |
| `modules/par/internal/services/linking.py` | Issue code or QR; redeem; revoke; consent tie-in | 140 |
| `modules/par/internal/services/overview.py` | Child overview from ANL, GAM and EXAM reads | 120 |
| `modules/par/internal/services/controls.py` | Controls; mode lock; time remaining; outbox | 110 |
| `modules/par/internal/jobs/weekly_report.py` | Saturday report and SMS | 130 |
| `modules/par/internal/routes/guardian.py` | Guardian routes | 130 |
| `modules/par/internal/routes/child_codes.py` | Child code issue | 40 |
| `modules/par/internal/schemas/parent.py` | Schemas | 120 |
| `modules/par/__init__.py` (modify) | Real `tutor_mode_lock`, `time_remaining_today`, `quiet_hours_for` | +40 |

**Identity (AUTH)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/auth/internal/providers/apple.py` | Identity token verification, code exchange, revoke | 150 |
| `modules/auth/internal/services/apple_notifications.py` | Webhook handling (JWS) | 110 |
| `modules/auth/internal/models/p1.py` | Device profile links, password credentials, email verifications, Apple notifications | 90 |
| `modules/auth/internal/services/password.py` | Sign-up, sign-in, lockout, breached check | 160 |
| `modules/auth/internal/services/password_reset.py` | Reset and email verification | 120 |
| `modules/auth/internal/services/shared_device.py` | Device–account links | 80 |
| `modules/auth/internal/routes/password.py` | Password routes | 110 |
| `modules/auth/internal/routes/devices.py` | Shared device routes | 60 |
| `modules/auth/internal/routes/apple_webhook.py` | Apple notifications | 40 |
| `modules/auth/internal/schemas/p1.py` | Schemas | 110 |

**Exam (EXAM)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/exam/internal/models/integrity.py` | Integrity events, anomaly flags, orders, set assignments | 100 |
| `modules/exam/internal/models/written_series.py` | Written answers and pages, series, items, standings, certificates | 120 |
| `modules/exam/internal/services/shuffle.py` | Seeded shuffle, set assignment, variant map (pure + persistence) | 150 |
| `modules/exam/internal/services/scoring_variants.py` | Scorer extension for variant keys | 80 |
| `modules/exam/internal/services/integrity_events.py` | Event batch intake, counts | 90 |
| `modules/exam/internal/services/anomaly_jobs.py` | IP, device and similarity detectors (DuckDB plus Postgres reads) | 160 |
| `modules/exam/internal/services/anomaly_review.py` | Console and decisions (audited) | 100 |
| `modules/exam/internal/services/written_exam.py` | Page upload, drafting, examiner marks, result merge | 160 |
| `modules/exam/internal/services/series.py` | Series, standings job | 140 |
| `modules/exam/internal/services/certificates.py` | Issue, verify, revoke; PDF enqueue | 130 |
| `modules/exam/internal/sql/similarity.sql` | DuckDB similarity query | 90 |
| `modules/exam/internal/routes/integrity.py` | Integrity and anomaly routes | 90 |
| `modules/exam/internal/routes/written.py` | Written exam and examiner routes | 90 |
| `modules/exam/internal/routes/series_certs.py` | Series and certificate routes | 110 |
| `modules/exam/internal/schemas/p1.py` | Schemas | 150 |

**Planner (PLAN)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/plan/internal/models/tracker.py` | Tracker, follows, eligibility targets and rules | 90 |
| `modules/plan/internal/models/email.py` | Email messages (G.3) | 40 |
| `modules/plan/internal/providers/apns.py` | APNs HTTP/2 adapter | 120 |
| `modules/plan/internal/providers/email_ses.py` | Email adapter (G.3) | 100 |
| `modules/plan/internal/services/tracker.py` | CRUD (audited), follow, change alerts | 140 |
| `modules/plan/internal/services/eligibility_rules.py` | Pure rules engine | 140 |
| `modules/plan/internal/services/eligibility.py` | Check endpoint service | 80 |
| `modules/plan/internal/services/sms_alerts.py` | PLAN-06 category allow-list, caps, consent scope | 100 |
| `modules/plan/internal/routes/tracker.py` | Tracker routes | 100 |
| `modules/plan/internal/routes/eligibility.py` | Eligibility routes | 60 |
| `modules/plan/internal/schemas/p1.py` | Schemas | 110 |

**Commerce (PAY)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/pay/internal/models/p1.py` | Subscriptions, family, proration, bundles, affiliates | 150 |
| `modules/pay/internal/providers/apple_iap.py` | App Store Server API verification and notifications JWS | 160 |
| `modules/pay/internal/services/subscriptions.py` | Create, renew, dunning, cancel | 160 |
| `modules/pay/internal/services/proration.py` | Quote and apply (pure + persistence) | 110 |
| `modules/pay/internal/services/family.py` | Family plan and members | 110 |
| `modules/pay/internal/services/beneficiary.py` | Pay for a linked child (PAR check) | 70 |
| `modules/pay/internal/services/affiliates.py` | Apply, attribution consumer, payouts | 150 |
| `modules/pay/internal/jobs/renewals.py` | Renewal scheduler | 90 |
| `modules/pay/internal/routes/subscriptions_family.py` | Routes | 130 |
| `modules/pay/internal/routes/affiliates.py` | Routes | 80 |
| `modules/pay/internal/routes/apple.py` | Apple purchase and webhook | 70 |
| `modules/pay/internal/schemas/p1.py` | Schemas | 140 |

**Operations (OPS)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `modules/ops/internal/models/growth.py` | Flags, campaigns, sends, experiments, assignments | 110 |
| `modules/ops/internal/services/flags.py` | Evaluation (pure) and admin | 140 |
| `modules/ops/internal/services/segments.py` | Segment DSL → query through module read interfaces | 150 |
| `modules/ops/internal/services/campaigns.py` | Schedule, send through PLAN, stats | 150 |
| `modules/ops/internal/services/experiments.py` | Sticky assignment (hash), admin | 100 |
| `modules/ops/internal/services/bi_reports.py` | Saved DuckDB reports, cache | 130 |
| `modules/ops/internal/sql/bi_*.sql` | One file per report (dau_wau, funnels, conversion, retention, revenue, ai_cost) | ≤ 100 each |
| `modules/ops/internal/routes/growth.py` | Flags, campaigns, experiments, BI | 140 |
| `modules/ops/internal/schemas/growth.py` | Schemas | 120 |

**Other modules**

| Path | Change |
|---|---|
| `modules/cms/internal/services/publish.py` (modify) | NFR-11 alt-text gate | 
| `modules/qb/internal/services/payloads.py` (modify) | `alt` and `aria_label` in `QuestionPayload` media |
| `modules/ai/internal/services/admission.py` (modify) | Parent time-cap check |
| `modules/prac/internal/services/session_start.py` (modify) | Parent time-cap check |
| `modules/nfr/internal/services/client_config.py` (modify) | Feature flags in `/v1/config/client` |
| `entrypoints/*` (modify) | Mount routers, register jobs |

### C.4 Background jobs

| Job kind | Trigger | Idempotency |
|---|---|---|
| `inst.roster.import` | On upload | `import_id` |
| `inst.omr_template.pdf`, `inst.paper.pdf` | On request | Row id |
| `inst.homework.remind` | Due − 24 h | `homework_id:user_id` |
| `par.weekly_report` | Saturday 10:00 Dhaka | `guardian:child:week_key` (table unique) |
| `plan.tracker.alert` | `tracker_item.changed` | `processed_events` |
| `exam.anomaly.scan` | Exam final + 1 h | `exam_id` |
| `exam.series.standings` | `exam.scored` | `processed_events` |
| `exam.certificate.issue` | Merit published / series complete | `certificate unique (user, kind, ref)` |
| `pay.subscription.renew` | Daily | `sub:{id}:{period_end}` |
| `pay.affiliate.attribute` | `payment.captured` | `order_id` unique |
| `pay.affiliate.payouts` | Monthly | `affiliate:period` |
| `ops.campaign.send` | Scheduled | `campaign_sends` PK |
| `ops.experiment.stats` | Hourly | Upsert |
| `auth.apple.revoke` | Account deletion | `user_id` |
| `qb.search.reindex_tenant` | Tenant content publish | `tenant:version` |

### C.5 Validation, errors and security

- Every workspace, roster, homework and private-question endpoint checks `can(actor, action, tenant_scope)`. A 404 is returned rather than a 403 for resources in other tenants, so existence never leaks.
- Linked parents see v2 §7.3's parent column only: assignment title, status, final marks, the teacher's summary. Never the private question text or the answer script, unless the workspace setting allows it.
- Guardian link redemption is rate limited at T-auth and caps at 10 failed codes per hour per account. Codes are 8 characters, valid for 24 h, single use.
- Collusion and anomaly evidence is visible only to `Staff:exam.integrity`. Students see nothing until a decision. Decisions are audited.
- Certificates: the verify endpoint returns only name (first name for minors), exam or series, rank band and issue date.
- Password policy: minimum 10 characters, a breached-password check (configurable), argon2id `m=64MiB, t=3, p=1` (tune in staging). Responses never say whether an email exists.
- Apple webhook: JWS signature chain verified against the Apple root CA; replays are deduped on `event_id`.
- Campaign segments cannot target users who opted out of the category. Minors are excluded from promotional SMS.

### C.6 Configuration

New settings:
- `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`, `APPLE_CLIENT_IDS`
- `APNS_KEY_ID`, `APNS_PRIVATE_KEY`, `APNS_TOPIC`
- `APP_STORE_ISSUER_ID`, `APP_STORE_KEY`
- `EMAIL_PROVIDER`, `EMAIL_FROM`

The prod validator refuses to start if Apple sign-in or IAP is enabled while any of its secrets are missing.

New `runtime_config` keys:
- `cms.require_alt_text`
- `par.weekly_sms_enabled`
- `plan.sms_alert_daily_cap`
- `pay.dunning_retries`
- `exam.anomaly.thresholds`
- `inst.omr.min_confidence`

---

## D. API contracts

Conventions are in [`14`](14_api_contracts.md) §1. "Tenant" means the actor must hold the role in that workspace (or batch) scope, checked through `can()`.

### D.1 Institutions

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/admin/workspaces` | `{institution_ref_id?, name, plan, admin_user_id}` | `Workspace{id, name, plan, status}` | Staff:inst.manage (audited) | Admin user exists | 409 `exists_for_institution` | T-admin / R |
| `GET /v1/workspaces/{id}` | – | `Workspace` + `branding`, `branches[]`, counts | Role:inst.admin or inst.teacher (tenant) | – | 404 | T-read / – |
| `PATCH /v1/workspaces/{id}` | `{name?, logo_upload_id?, branding?: {primary_color, header_text_bn}}` | `Workspace` | Role:inst.admin (tenant, audited) | Logo moderated; colour hex | 422 | T-write / – |
| `POST /v1/workspaces/{id}/branches` / `PATCH …/{bid}` | `{name, address?}` | `Branch` | Role:inst.admin | Unique name per workspace | 409 | T-write / R |
| `POST /v1/workspaces/{id}/members` | `{user_id or phone, role: admin|teacher|staff, branch_id?}` | `Member` | Role:inst.admin (audited) | Teachers must hold an approved teacher account (B6) | 422 `teacher_not_approved` | T-write / R |
| `DELETE /v1/workspaces/{id}/members/{uid}` | – | 204 | Role:inst.admin | Cannot remove the last admin | 409 `last_admin` | T-write / – |
| `POST /v1/workspaces/{id}/batches` | `{name, kind: batch|section, subject_node_id, branch_id?, teacher_user_id}` | `Batch` (with join code) | Role:inst.admin | Teacher is a member | 422 | T-write / R |
| `POST /v1/workspaces/{id}/roster:import` | `{file_upload_id, batch_id?}` (CSV: roll_no, name, guardian_phone?) | `{import_id, status}` | Role:inst.admin | ≤ 5,000 rows; UTF-8 | 422 | T-write / R |
| `POST /v1/workspaces/{id}/roster/invites` | `{roster_entry_ids[] or batch_id, channel: sms|code}` | `{sent, codes?: [{roster_entry_id, code}]}` | Role:inst.admin | Guardian consent scope for SMS to minors | 422 | T-write / R |
| `POST /v1/roster:claim` | `{code}` | `{workspace_id, batch_id, entitlement_id?}` | User (consent if under 18) | Code valid; seat available | 403 `consent_required`, 409 `no_seats`, 410 `expired` | T-write / R |
| `GET /v1/workspaces/{id}/seats` | – | `{allocations: [{id, product_id, seats_total, seats_used, valid_to}]}` | Role:inst.admin | – | – | T-read / – |
| `POST /v1/workspaces/{id}/seats` | `{product_id, seats_total, valid_to}` | Allocation | Staff:pay.grant or Role:inst.admin with a paid licence order | – | 403 | T-write / R |
| `POST /v1/workspaces/{id}/questions` / `PATCH …/{qid}` | B2 question create and edit payload | B2 response with `tenant_id` | Role:inst.teacher (tenant) | Same as B2, plus tenant rules | 422 | T-write / R |
| `POST /v1/workspaces/{id}/exams` | `{batch_id, blueprint_id or question_version_ids[], starts_at, ends_at, result_publish_at, solution_unlock_at, shuffle: bool, sets: 1–4}` | `Exam` | Role:inst.teacher (tenant) | Versions are platform or this tenant | 404 for other-tenant ids | T-write / R |
| `GET /v1/workspaces/{id}/exams/{eid}/merit` | `?cursor` | `Page<{rank, roll_no, name, score}>` | Role:inst.teacher (tenant) | – | 404 | T-read / – |
| `POST /v1/workspaces/{id}/omr-templates` | `{question_count 10–200, options 4|5, roll_digits 4–10}` | `{template_id, pdf_url (signed)}` | Role:inst.teacher | – | 422 | T-write / R |
| `POST /v1/workspaces/{id}/omr-scans` | `{exam_id, template_id, roster_entry_id or roll_no, image_upload_id, detected: {roll, answers: [{q, marks[]}]}, confidence 0–1}` | `{scan_id, status: graded|needs_review, attempt_id?}` | Role:inst.teacher | Grid matches the template; confidence threshold | 422 `grid_mismatch` | T-upload / R |
| `POST /v1/workspaces/{id}/paper-generations` | `{exam_id, sets: ["A".."D"], header: {name_bn, exam_name, date}}` | `{id, status}` | Role:inst.teacher | Exam in tenant | 404 | T-write / R |
| `GET /v1/workspaces/{id}/analytics` | `?batch_id&compare_batch_id?&user_id?` | `{weak_chapters[], participation, comparison?}` | Role:inst.teacher (tenant) | Student is a batch member | 404 | T-read / – |
| `POST /v1/workspaces/{id}/homework` | `{batch_id, kind: practice|written, title, spec, written_task_id?, due_at}` | `Homework` | Role:inst.teacher | `due_at` in the future | 422 | T-write / R |
| `GET /v1/me/homework` | `?status&cursor` | `Page<{id, title, kind, due_at, status, marks?}>` | User | – | – | T-read / – |

### D.2 Parents and shared devices

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/me/guardian-link-codes` | – | `{code, qr_payload, expires_at}` | User (the child) | ≤ 5 active codes | 409 `limit_reached` | T-write / R |
| `POST /v1/guardian/links` | `{code}` | `{link_id, child: {id, first_name}}` | User (becomes guardian) | Not self; not already linked | 410 `expired`, 409 `already_linked`, 429 | T-auth / R |
| `DELETE /v1/guardian/links/{id}` | – | 204 | Guardian or child of the link (audited) | – | 404 | T-write / – |
| `GET /v1/guardian/children` | – | `{children: [{id, first_name, tracks[], link_id}]}` | Role:guardian | – | – | T-read / – |
| `GET /v1/guardian/children/{child_id}/overview` | `?period=7d|30d` | `{study_minutes, streak, exams: [...], score_trend, rank_trend, weak_subjects[]}` | Active link | – | 404 | T-read / – |
| `GET /v1/guardian/children/{child_id}/reports` | `?cursor` | `Page<{week_key, summary, sent_sms_at}>` | Active link | – | 404 | T-read / – |
| `GET /v1/guardian/children/{child_id}/controls` | – | `{tutor_mode_lock, daily_time_cap_min, quiet_start, quiet_end}` | Active link | – | 404 | T-read / – |
| `PUT /v1/guardian/children/{child_id}/controls` | Same fields; cap 15–600 or null | Controls | Active link (audited security event) | Quiet window valid | 422 | T-write / – |
| `POST /v1/devices/{device_id}/profiles` | `{}` (uses the caller's session) | `{device_id, user_id}` | User whose session is on that device | ≤ 5 accounts per device | 409 `limit_reached` | T-write / O |
| `GET /v1/devices/{device_id}/profiles` | – | `{profiles: [{user_id, first_name}]}` | User with a session on that device | – | 404 | T-read / – |
| `DELETE /v1/devices/{device_id}/profiles/{user_id}` | – | 204 | That user, or any account on the device (removal only) | – | 404 | T-write / – |

### D.3 Identity additions

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/auth/social/apple` (existing route, `provider=apple`) | `{id_token, authorization_code, nonce, device, name?}` | `TokenPair` | Public | Nonce single-use; aud ∈ Apple client ids; age gate | 401 `invalid_token`, 403 `age_restricted`, 409 `identity_in_use` | T-auth / O |
| `POST /v1/me/identities/apple` | Same | `{linked: true}` | User | As above | 409 | T-auth / O |
| `POST /v1/auth/password/sign-up` | `{email, password, display_name, date_of_birth, device}` | `{verification_sent: true}` | Public | Password policy; email format | 422 (generic, never reveals an existing email) | T-auth / O |
| `POST /v1/auth/password/sign-in` | `{email, password, device}` | `TokenPair` | Public | Locked account → generic 401 | 401, 429 | T-auth / – |
| `POST /v1/auth/password/reset` | `{email}` | 202 always | Public | – | 429 | T-otp / – |
| `POST /v1/auth/password/reset/confirm` | `{token, new_password}` | 204; revokes all sessions | Public | Token valid and unused | 410 `expired` | T-auth / – |
| `POST /v1/auth/email/verify` | `{token}` | 204 | Public | – | 410 | T-auth / – |
| `POST /v1/webhooks/apple/notifications` | Apple JWS `payload` | 200 | Signed (Apple JWS) | Dedupe on `event_id` | 400 bad signature | T-webhook / – |

### D.4 Exam integrity, written exams, series and certificates

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/exam-attempts/{id}/integrity-events` | `{events: [{kind: app_switch|blur|screenshot_attempt|split_screen, occurred_at, count}]}` (≤ 50) | `{accepted}` | Owner of attempt | Attempt in progress or ≤ 10 min after end | 409 `attempt_closed` | T-write / O |
| `GET /v1/admin/exams/{id}/anomalies` | `?kind&status&cursor` | `Page<{flag_id, attempt_id, kind, score, evidence_summary, status}>` | Staff:exam.integrity | – | – | T-admin / – |
| `POST /v1/admin/anomalies/{id}:decide` | `{decision: clear|confirm, note, action?: invalidate_attempt}` | Flag | Staff:exam.integrity (audited); invalidation also needs Staff:exam.publish | `note` required | 409 `already_decided` | T-admin / R |
| `POST /v1/exam-attempts/{id}/written-answers/{qv_id}/pages` | `{page_no, upload_id, sha256}` | `{written_answer_id, page_no}` | Owner; exam has a written section | Page ≤ 10 per question; before hard close | 409 `exam_closed`, 422 | T-upload / R |
| `GET /v1/admin/exams/{id}/written-queue` (G.4) | `?status&cursor` | `Page<{written_answer_id, question, draft_total?, flags}>` | Staff:exam.examiner | – | – | T-admin / – |
| `POST /v1/admin/written-answers/{id}/marks` (G.4) | `{parts: [{rubric_point_id, marks, note?}]}` | `{grading_id, total}` | Staff:exam.examiner (audited) | Marks ≤ rubric marks | 422 | T-admin / R |
| `GET /v1/exam-series` | `?track_id` | `{items: [{id, title, product_id, exams_count, next_exam_at}]}` | User | – | – | T-read / – |
| `GET /v1/exam-series/{id}/standings` | `?cursor` | `Page<{rank, display_name, institution?, total_score, exams_taken, is_me}>` | User (entitled or public setting) | Minors' privacy | 403 | T-read / – |
| `GET /v1/certificates` | – | `{items: [{id, kind, title, issued_at, pdf_url}]}` | User | – | – | T-read / – |
| `GET /v1/certificates/verify/{code}` | – | `{valid, revoked, holder_name, kind, title, rank_band, issued_at}` | Public | Code format | 404 | T-read / – |
| `POST /v1/admin/exam-series` / `PATCH …/{id}` | `{track_id, title_bn, title_en, product_id, exam_ids[], certificate_rule}` | Series | Staff:exam.manage (audited) | Exams exist | 422 | T-admin / R |

### D.5 Planner

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/tracker` | `?track_id&kind&from&to&cursor` | `Page<TrackerItem>` + `followed: bool` | User | – | – | T-read / – |
| `PUT /v1/tracker/{item_id}/follow` | – | `{following: true}` | User | – | 404 | T-write / – |
| `DELETE /v1/tracker/{item_id}/follow` | – | 204 | User | – | – | T-write / – |
| `POST /v1/eligibility:check` | `{ssc_gpa?, hsc_gpa?, passing_years, group, age_on?, subjects[]?, target_kinds[]}` | `{eligible: [{target_id, name}], not_eligible: [{target_id, reasons[]}]}` | User | Ranges (GPA 0–5) | 422 | T-read / – |
| `POST /v1/admin/tracker` / `PATCH …/{id}` | `TrackerItem` fields | Item | Staff:plan.tracker (audited) | `closes_at ≥ opens_at` | 422 | T-admin / R |
| `POST /v1/admin/eligibility-rules` / `PATCH …/{id}` | `{target_id, rule}` (new version on change) | Rule | Staff:plan.tracker (audited) | Rule schema | 422 `invalid_rule` | T-admin / R |

### D.6 Commerce

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `POST /v1/store/purchases/apple` | `{signed_transaction}` | `{entitlement_id, status}` | User | JWS chain; bundle id; not already used | 409 `already_used`, 422 | T-write / R |
| `POST /v1/webhooks/apple-store` | App Store Server Notification v2 `signedPayload` | 200 | Signed | Dedupe `notificationUUID` | 400 | T-webhook / – |
| `GET /v1/me/subscriptions` | – | `{items: [{id, product, provider, status, current_period_end, next_charge_at}]}` | User | – | – | T-read / – |
| `POST /v1/me/subscriptions` | `{product_id, provider}` | `{subscription_id, next_action: {redirect_url|sdk_payload}}` | User | Provider supports tokenisation (capability flag) | 422 `not_supported` | T-write / R |
| `DELETE /v1/me/subscriptions/{id}` | – | `{cancel_at}` (period end) | Owner | – | 404 | T-write / – |
| `POST /v1/me/subscriptions/{id}:change` | `{to_product_id, confirm_quote_id?}` | Without confirm: `ProrationQuote`; with: `{order_id}` | Owner | Quote unexpired | 410 `quote_expired` | T-write / R |
| `POST /v1/family-plans` | `{product_id}` | `{plan_id, order_id}` | User (guardian) | Product kind is family | 422 | T-write / R |
| `POST /v1/family-plans/{id}/members` | `{child_user_id}` | `{member, entitlement_id}` | Plan owner; child is linked | Under `max_members` | 409 `plan_full`, 403 `not_linked` | T-write / R |
| `POST /v1/orders` (existing; adds `beneficiary_user_id`) | + `beneficiary_user_id?` | As B6 | Beneficiary must be a linked child | – | 403 `not_linked` | T-write / R |
| `POST /v1/affiliates` | `{institution?, campus?, payout_method}` | `{affiliate_id, code, status: pending}` | User (adult) | Age ≥ 18 | 403 `age_restricted` | T-write / R |
| `GET /v1/affiliates/me/report` | `?period` | `{signups, orders, commission_poisha, payouts[]}` | Role:affiliate | – | – | T-read / – |
| `POST /v1/admin/affiliate-payouts:run` | `{period}` | `{payouts, total_poisha}` | Staff:pay.finance (audited) | Closed period | 409 `already_run` | T-admin / R |

### D.7 Operations

| Endpoint | Request | Response | AuthZ | Validation | Errors | RL / Idem |
|---|---|---|---|---|---|---|
| `GET /v1/admin/feature-flags` | – | `{flags: [...]}` | Staff:ops.config | – | – | T-admin / – |
| `PUT /v1/admin/feature-flags/{key}` | `{enabled, rules: [{attr, op, value}], rollout_pct 0–100, payload?}` | Flag | Staff:ops.config (audited) | Rule schema | 422 | T-admin / R |
| `POST /v1/admin/campaigns` / `PATCH …/{id}` | `{name, channel: push|sms|email, segment, content: {bn, en}, experiment_id?, schedule_at?}` | Campaign | Staff:ops.campaign (audited) | Segment DSL valid; template placeholders | 422 | T-admin / R |
| `POST /v1/admin/campaigns/{id}:send` | `{mode: now|scheduled, dry_run?: bool}` | `{estimated_recipients, status}` | Staff:ops.campaign (audited); SMS above 10,000 recipients also needs Staff:ops.approve | Cost estimate shown | 409 `already_sent` | T-admin / R |
| `POST /v1/admin/experiments` / `PATCH …/{id}` | `{key, variants: [{name, weight}], starts_at, ends_at}` | Experiment | Staff:ops.campaign | Weights sum to 100 | 422 | T-admin / R |
| `GET /v1/admin/bi/{report}` | `report ∈ {dau_wau, funnels, conversion, retention, revenue, ai_cost}`; `?from&to&track&district` | `{columns[], rows[], computed_at}` | Staff:ops.bi | Range ≤ 400 days | 404 unknown report | T-admin / – |
| `GET /v1/config/client` (existing) | – | Adds `flags: {key: value}` evaluated for the caller | Public / User | – | – | T-read / – |
| `POST /v1/push-tokens` (existing) | Adds `platform: apns` | – | – | – | – | – |

---

## E. Testing strategy

| Kind | Files | Cases |
|---|---|---|
| **Cross-tenant (gate)** | `tests/contract/test_cross_tenant.py` (generated) | For every route tagged `tenant` in OpenAPI: actor of tenant A requests tenant B's resource ids → 404 and no data. Runs with RLS off (application filters) and RLS on. |
| Cross-tenant: stores | `tests/contract/test_tenant_search_cache.py` | Tenant B's private question never appears in learner search, similar questions, photo match, canonical cache, item statistics or trends. Redis keys contain the tenant segment. |
| RLS DB | `tests/modules/nfr/db/test_rls_policies.py` | Direct SQL as `app_api`: no rows without context; `SET LOCAL` does not leak to the next transaction on the same connection (PgBouncer simulation); break glass writes an audit row first |
| RLS performance | `tests/modules/nfr/db/test_rls_explain.py` | `EXPLAIN` on session start, answer path, search: index use, no seq scan on tenant tables |
| Unit | `tests/modules/exam/unit/test_shuffle.py` | Deterministic per seed; uniform set distribution; canonical-label scoring identical to unshuffled |
| Unit | `tests/modules/plan/unit/test_eligibility_rules.py` | Table-driven rules: GPA thresholds, group, age on date, any/all |
| Unit | `tests/modules/pay/unit/test_proration.py` | Day-based pro rata, rounding to whole poisha (floor), never negative |
| Unit | `tests/modules/ops/unit/test_flags.py` | Rollout hash stable; attribute operators; default when malformed |
| Unit | `tests/modules/exam/unit/test_similarity.py` | Known colluding pair scores above threshold; independent pair below |
| Integration | `tests/modules/inst/integration/test_roster_claim_seats.py` | 20 concurrent claims for 10 seats → exactly 10 entitlements (concurrency) |
| Integration | `tests/modules/inst/integration/test_omr_grading.py` | Scan → attempt → `exam_results` → notebook; replay of the same scan idempotent; low confidence → `needs_review` |
| Integration | `tests/modules/par/integration/test_controls_enforced.py` | Time cap blocks a new session and AI admission; quiet hours hold push; mode lock forces Socratic |
| Integration | `tests/modules/par/integration/test_weekly_report.py` | One report per (guardian, child, week); SMS 2 segments of Bangla; respects `par.weekly_sms_enabled` |
| Integration | `tests/modules/exam/integration/test_written_exam.py` | Pages → AI draft → examiner marks → final; written marks excluded from national merit |
| Integration | `tests/modules/exam/integration/test_series_certificates.py` | Standings from final results; certificate issued once; verify shows revoked |
| Integration | `tests/modules/pay/integration/test_subscription_renewal.py` | One order per period under two concurrent schedulers; dunning 3 tries; cancel at period end |
| Integration | `tests/modules/pay/integration/test_family_plan.py` | `max_members` enforced concurrently; entitlement to the beneficiary |
| Integration | `tests/modules/pay/integration/test_apple_iap.py` | Signed fixtures (test CA); duplicate transaction refused; refund notification revokes the entitlement |
| Integration | `tests/modules/auth/integration/test_apple_signin.py` | Token verify, nonce reuse refused, code exchange stored encrypted, deletion → revoke job |
| Integration | `tests/modules/auth/integration/test_password.py` | Lockout after 10; reset revokes sessions; no email enumeration (identical responses and timing within 50 ms) |
| API | `tests/modules/*/api/test_*_b08.py` | Every endpoint in §D: success, validation, authorization, idempotent replay |
| Authorization | `tests/modules/par/api/test_parent_visibility.py` | Parent sees marks but not private question text or answer script (v2 §7.3) |
| Regression | B1–B7 suites | Unchanged; the answer-path latency budget holds with RLS on |
| Failure | `tests/modules/plan/integration/test_apns_failures.py` | 410 `Unregistered` invalidates the token; 429 backs off |
| Failure | `tests/modules/ops/integration/test_campaign_resume.py` | Worker crash mid-send resumes without duplicate sends |
| Performance | `tests/load/b08_tenant_mix.js` | 50% tenant users: p95 regression ≤ 10% vs B7 baseline |

**Coverage:** ≥ 85% overall. ≥ 95% on:
- `core/db_tenant.py`
- `ops/internal/services/break_glass.py`
- `auth/internal/services/{tenants,password}.py` and `auth/internal/providers/apple.py`
- `inst/internal/services/roster_claim.py`
- `exam/internal/services/{shuffle,scoring_variants}.py`
- `pay/internal/services/{subscriptions,proration,family}.py` and `pay/internal/providers/apple_iap.py`
- `par/internal/services/controls.py`

---

## F. Build completion

### F.1 Acceptance criteria

1. The cross-tenant suite passes with RLS disabled and with RLS enabled, with zero findings.
2. RLS is enabled on every tenant table in production-like staging; latency regression stays within budget (≤ 10% p95).
3. All 32 P1 IDs, plus Apple and email/password sign-in, are demonstrated by API tests mapped in the traceability matrix.
4. Concurrency: seat, family-plan and renewal tests produce exact counts.
5. An exam with shuffle and 4 sets scores identically to the unshuffled reference on 10,000 synthetic attempts.
6. Anomaly jobs flag every injected colluding pair in the fixture, with false positives ≤ 2% on independent pairs.
7. Parent controls take effect within 30 s of a change (cache invalidation test).
8. An Apple account-deletion notification leads to the token being revoked and the identity unlinked within 1 h (job SLA).
9. **Synthetic-data acceptance and calibration (R-29).** Items 5 and 6 and the INST-07 batch analytics are accepted on synthetic fixtures, because no real cohort exists before the frontend. Collusion thresholds and anomaly scores carry `calibration: "synthetic"` until the post-launch calibration gate (B7 §F.1 item 11, and [`20`](20_risk_register.md)) re-validates them on the first 3 real live exams, judged by the false-positive rate in ops review. Until then anomaly flags are advisory only and never block a result.
10. **Tenant vector search (R-23).** For a tenant with a partial HNSW index and for a small tenant on exact search, filtered recall@10 is ≥ 0.9 against exact search, and no other tenant's rows appear.

### F.2 Deliverables

Migrations `b08_01`–`b08_18`; module code per §C.3; RLS helpers and checks; provider adapters (APNs, Apple sign-in, Apple IAP, email); PDF templates; a runbook for break glass, RLS rollback and the Apple deletion flow; updated OpenAPI snapshot; the build report.

### F.3 Definition of done

Per [`21`](21_definition_of_done.md), plus:
- `scripts/check_tenant_tx.py` is clean.
- A security review sign-off on the RLS design and break-glass flow is recorded in the PR.

### F.4 Manual verification checklist

- [ ] Create two workspaces with a private question each. As a teacher of A, search for B's question text and expect no result. Check the Redis keys in staging.
- [ ] Enable RLS through the migration; repeat; then roll back with the downgrade and confirm the app still works.
- [ ] Break glass as a super admin with a reason; confirm the audit row precedes the read.
- [ ] Import a 500-row CSV roster with 3 bad rows; claim 2 entries; check seats and entitlements.
- [ ] Print an OMR template; submit a detected grid; the student's result and notebook update.
- [ ] Link a parent; set a 30-minute cap; the child's next session after the cap is refused with `403 time_cap_reached`.
- [ ] Run a 4-set shuffled exam in staging; download the merit list.
- [ ] Sign in with Apple on a TestFlight build (or the sandbox); delete the account; confirm revocation in the logs.
- [ ] Send a dry-run campaign and check the recipient estimate excludes opted-out users and minors (SMS).

### F.5 Exit criteria before Build 9

F.1–F.4 are done; RLS is enabled in staging for 7 days with no isolation incidents; supervisor approval of the §G additions is recorded in `01` and `14`.

---

## G. Proposed additions (accepted)

All items were **accepted** during integration and are now in [`01`](01_database_design.md) §3 and §4.E and in [`14`](14_api_contracts.md). The `family_plan` and `reward_store` entitlement sources are the final names.

| # | Addition | Why | Change |
|---|---|---|---|
| G.1 | `tenant_id uuid NULL` on `qbank.question_versions` and `qbank.qv_content` (denormalised from `questions`) | RLS needs a local column; versions are read by id on hot paths | `01` §3.7 |
| G.2 | `identity.external_identities.provider_refresh_token_enc bytea NULL` (Apple only) | Apple's account-deletion token revocation needs the refresh token. This is an exception to "provider tokens are never stored". | `01` §3.2; note in `18` |
| G.3 | Email transport in PLAN: `notify.email_messages` P (PK `(id, created_on)`, `to_email_hash`, `to_email_enc`, `template_code`, `lang`, `provider`, `provider_msg_id`, `status`, `purpose`, `sent_at`, `error`) and `notify.templates.channel` value `email` | Password reset and verification (AUTH-01) and email campaigns (OPS-05) need email; no transport exists | `01` §3.4 (B8) |
| G.4 | Endpoints `GET /v1/admin/exams/{id}/written-queue` and `POST /v1/admin/written-answers/{id}/marks` (Staff:exam.examiner) | EXAM-10 requires a human-examiner rubric UI; the B6 teacher queue is batch-scoped, not exam-scoped | `14` §3.11 (B8) |
| G.5 | `commerce.entitlements.source` value `family_plan` | Family members' entitlements need a distinct source for refunds and reports | `01` §4 commerce |
| G.6 | Permission codes `exam.examiner`, `exam.integrity`, `platform.break_glass`, `ops.approve`, `mentor.reply` (if not seeded in B7) | New staff actions | `identity.permissions` seed |

**Inconsistency noted:** `01` §1 says "Row-level security policies are added in Build 8". This build adds them but **enables** them only after the context code is deployed (two migrations), which matches the expand/contract rule in `03`.

# 03 · Database migration plan

**Date:** 2026-11-27 · **Tables and columns:** [`01_database_design.md`](01_database_design.md) §3–§4 · **Build order:** [`04_backend_master_plan.md`](04_backend_master_plan.md) §6

This document fixes how schema changes are written, tested and deployed, and lists every migration in build order. No migration is executed during planning.

---

## 1. Alembic setup

| Item | Decision |
|---|---|
| Location | `backend/migrations/` (`env.py`, `script.py.mako`, `helpers/`, `versions/`) |
| Driver | **asyncpg**. `env.py` builds an async engine from `settings.migration_database_url` (direct to RDS with the owner role, never through PgBouncer) and runs migrations with `connection.run_sync(do_run_migrations)`. |
| Metadata | `target_metadata = app.core.db.Base.metadata`. `env.py` imports `app.modules.registry.import_all_models()`, which imports each module's `internal/models` package, so autogenerate and `alembic check` see every table. |
| Naming convention | Set once on `Base.metadata`: `ix: "ix_%(table_name)s_%(column_0_N_name)s"`, `uq: "uq_%(table_name)s_%(column_0_N_name)s"`, `ck: "ck_%(table_name)s_%(constraint_name)s"`, `fk: "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"`, `pk: "pk_%(table_name)s"`. Names longer than 63 bytes are shortened by a deterministic hash suffix in `helpers/naming.py`. |
| Schemas | `include_schemas=True`. `include_object` filters out partitions (`*_pNN`, `*_YYYYMM`, `*_YYYYMMDD`), because partitions are created by helpers and the maintenance job, not by models. |
| Version table | `platform.alembic_version` |
| Revision ids | Explicit, not random: `bNN_MM_<slug>`, where `NN` = build and `MM` = order within the build. Example: `b03_02_attempt_answers`. File name = revision id (`file_template = %%(rev)s`). The linear order is checked by a test (`down_revision` of each file = the previous id). |
| Roles | `app_owner` owns schemas and runs migrations. `app_rw` is used by the deployables: `SELECT, INSERT, UPDATE, DELETE` per schema, minus `UPDATE, DELETE` on append-only tables (`ops.audit_log`, `rewards.reward_transactions`, `practice.attempt_answers`, `exam.exam_answer_batches`, `commerce.entitlement_events`). `app_ro` is for replicas and analytics. Grants are made in the migration that creates each table, through `helpers/grants.py`. |
| Session settings in every migration | `SET lock_timeout = '3s'; SET statement_timeout = '15min';` from `env.py`. A migration that cannot get its lock within 3 s fails and is retried by the deploy job up to 3 times, rather than queueing behind traffic. |

### 1.1 `migrations/helpers/` (handwritten, each file ≤ 200 lines)

| Function | File | Behaviour |
|---|---|---|
| `create_hash_partitions(table, modulus)` | `partitions.py` | Creates `table_p00 … p{modulus-1}` with `FOR VALUES WITH (MODULUS m, REMAINDER r)`. Used for `attempt_answers` and `reward_transactions` (64). |
| `create_range_partitions(table, unit, start, count)` | `partitions.py` | Creates daily (`_YYYYMMDD`) or monthly (`_YYYYMM`) partitions from `start` for `count` periods. Used at table creation; later partitions are created by the maintenance job (§8). |
| `attach_default_partition(table)` | `partitions.py` | Creates `table_default` for range tables, so a missing partition never fails a write. The maintenance job alerts if a default partition holds any rows. |
| `add_check_in(table, column, values, name)` | `checks.py` | Adds `CHECK (column IN (...))` as `NOT VALID`, then `VALIDATE CONSTRAINT` in a separate statement (no long exclusive lock). |
| `swap_check_in(table, name, values)` | `checks.py` | Expand step for enum-like columns: add the new constraint `NOT VALID`, validate it, drop the old one, in one migration. |
| `enable_rls(table, policy_sql)` | `rls.py` | `ALTER TABLE … ENABLE ROW LEVEL SECURITY` plus the tenant policy using `current_setting('app.tenant_id', true)`. Does **not** `FORCE` it. `FORCE` is a separate contract migration (§9). |
| `grant_app(table, append_only=False)` | `grants.py` | Grants to `app_rw` and `app_ro`. |
| `create_index_concurrently(...)` | `indexes.py` | Wraps `op.create_index(..., postgresql_concurrently=True)` inside `op.get_context().autocommit_block()`. |

## 2. The 200-line rule for migrations

Every migration file is handwritten or hand-edited and counts toward the rule (it is checked by `scripts/check_file_length.py`).

- **One migration per table group**, normally 1–4 tables of one schema that are created together. Autogenerate is used only as a draft. The file is then edited to use the helpers, add CHECKs and grants, and remove noise.
- **Large tables get their own migration.** Examples: `attempt_answers` (64 partitions created by the helper in a loop, 6 indexes); `exam_answer_batches` with `exam_answers_latest`; `search_documents`.
- **Seed data is never inline.** Seeds load from versioned files in `migrations/seeds/` (CSV or JSON; data files are not source code, so they are not subject to the rule) through `helpers/seed.py`, which upserts by natural key.
- **Index-only migrations** (concurrent builds) are separate files, because they run outside a transaction.
- A migration that would exceed 200 lines is split into `bNN_MMa_*` and `bNN_MMb_*`. Fragmenting below about 40 lines without a reason is avoided.

## 3. Ordered migration list

Every table in `01` §3 appears exactly once in the build that creates it. "Alters" are expand steps on existing tables. **Depends** lists cross-schema foreign-key targets that must already exist.

### Build 1: platform foundation, identity and safety

| Revision | Creates or alters | Depends |
|---|---|---|
| `b01_01_schemas_roles` | All 16 schemas (`platform`, `identity`, `community`, `notify`, `ops`, `curriculum`, `qbank`, `cms`, `practice`, `exam`, `analytics`, `ai`, `rewards`, `commerce`, `institution`, `parent`); extensions `pgvector`, `pg_trgm`, `ltree`, `btree_gist`; roles `app_rw`, `app_ro` (if missing); test `test_registry_matches_migration` | — |
| `b01_02_platform_queue` | `platform.jobs` (with `status`, `dedupe_until`; the `queue` CHECK is generated from `app.core.jobs.queues.QUEUES`, so the migration imports that tuple, which has no other dependencies), `platform.dead_jobs`, `platform.processed_events` (P, daily; with `relay_batch_id`) | 01 |
| `b01_03_platform_outbox` | `platform.outbox` (P, daily), `platform.relay_checkpoints` | 01 |
| `b01_04_platform_misc` | `platform.idempotency_keys`, `platform.runtime_config` (+ seed defaults: kill switches off, min app version) | 01 |
| `b01_05_ops_audit` | `ops.audit_log` (P, monthly; append-only grants) | 01 |
| `b01_06_identity_reference` | `identity.districts`, `identity.upazilas`, `identity.institutions` (+ seeds: 64 districts plus sentinel `0` National, upazilas; institutions loaded by a job from the EIIN list, not a migration) | 01 |
| `b01_07_identity_users` | `identity.users`, `identity.external_identities` | 06 |
| `b01_08_identity_sessions` | `identity.otp_challenges`, `identity.device_sessions`, `identity.refresh_tokens` | 07 |
| `b01_09_identity_rbac` | `identity.roles`, `identity.permissions`, `identity.role_permissions`, `identity.role_grants` (+ seeds: 8 roles, permission codes, mapping) | 07 |
| `b01_10_identity_profile_consent` | `identity.profiles`, `identity.consent_documents`, `identity.guardian_consents`, `identity.privacy_settings`, `identity.data_requests` (moved from B6 for the Meta data-deletion status) (+ seed consent v1 bn/en) | 07, 06 |
| `b01_11_community_moderation` | `community.moderation_terms`, `community.moderation_decisions`, `community.content_reports`, `community.user_restrictions` (+ seed term list from `seeds/moderation_terms_v1.csv`) | 07 |
| `b01_12_notify_sms` | `notify.sms_messages` (P, monthly), `notify.templates` (+ seed OTP and consent templates bn/en) | 01 |

### Build 2: curriculum, question bank and content workflow

| Revision | Creates or alters | Depends |
|---|---|---|
| `b02_01_curriculum_core` | `curriculum.boards` (+ seed), `curriculum.tracks`, `curriculum.track_levels`, `curriculum.syllabus_versions` | B1 |
| `b02_02_taxonomy_nodes` | `curriculum.taxonomy_nodes` (ltree path, GiST), `curriculum.track_exam_dates` | 01 |
| `b02_03_identity_enrolments` | `identity.track_enrolments` | 01, b01_07 |
| `b02_04_qbank_questions` | `qbank.questions`, `qbank.question_versions`, `qbank.qv_content` | 02 |
| `b02_05_qbank_cq` | `qbank.cq_subparts`, `qbank.rubric_points` | 04 |
| `b02_06_qbank_mapping_media` | `qbank.question_node_map`, `qbank.question_media`, `qbank.rendering_failures`, `qbank.concept_notes` | 04, 02 |
| `b02_07_qbank_papers` | `qbank.papers`, `qbank.paper_items`, `qbank.paper_tracks` | 04, 01 |
| `b02_08_qbank_imports` | `qbank.import_jobs`, `qbank.import_rows` | 04 |
| `b02_09_cms_workflow` | `cms.workflow_events`, `cms.key_verifications`, `cms.review_assignments`, `cms.editor_drafts` | 04 |
| `b02_10_cms_error_reports` | `cms.error_reports` | 04 |
| `b02_11_platform_search` | `platform.search_documents` (without `embedding`); GIN and trigram indexes | 04 |
| `b02_12_qbank_fk_concept_note` | Alter `qbank.question_versions` add FK `concept_note_id → concept_notes` (`NOT VALID` then validate) | 06 |

### Build 3: learning loop and gamification core

| Revision | Creates or alters | Depends |
|---|---|---|
| `b03_01_practice_sessions` | `practice.practice_sessions`, `practice.session_items` | B2 |
| `b03_02_attempt_answers` | `practice.attempt_answers` (P, hash 64) + local indexes; **no outgoing FKs** (01 §1.1 exception); grants allow `UPDATE` only for the one-time `is_correct` set on self-marked rows (`WHERE is_correct IS NULL`, enforced in the service) | B2 |
| `b03_03_practice_derived` | `practice.score_adjustments`, `practice.mistake_entries` | 02 |
| `b03_04_practice_personal` | `practice.bookmark_folders`, `practice.bookmarks`, `practice.question_notes` | B2 |
| `b03_05_analytics_core` | `analytics.topic_progress` (fillfactor 80), `analytics.daily_study`, `analytics.projection_versions` (+ seed v1 active), `analytics.rebuild_audits` | B2 |
| `b03_06_rewards_rules_ledger` | `rewards.reward_rules` (+ seed v1), `rewards.reward_transactions` (P, hash 64; no outgoing FKs) | B1 |
| `b03_07_rewards_state` | `rewards.user_totals`, `rewards.daily_activity`, `rewards.streak_state`, `rewards.streak_days` | 06 |
| `b03_08_rewards_social` | `rewards.friend_codes`, `rewards.friend_links`, `rewards.board_flags`, `rewards.leaderboard_snapshots` | B1 |
| `b03_09_commerce_catalogue` | `commerce.products`, `commerce.product_grants`, `commerce.quota_policies` (+ seed v1 free and paid quotas) | B2 |
| `b03_10_commerce_entitlements` | `commerce.entitlements`, `commerce.entitlement_events` | 09 |
| `b03_11_notify_inbox` | `notify.notifications` (P, monthly), `notify.deliveries` (P, monthly), `notify.push_tokens`, `notify.preferences` | B1 |
| `b03_12_cms_corrections` | `cms.corrections` | B2 |

### Build 4: AI tutor platform

| Revision | Creates or alters | Depends |
|---|---|---|
| `b04_01_ai_threads` | `ai.tutor_threads`, `ai.tutor_messages` (P, monthly), `ai.tutor_citations` (P, monthly) | B3 |
| `b04_02_ai_usage_cost` | `ai.ai_usage` (P, monthly), `ai.cost_budgets`, `ai.pending_questions` | 01 |
| `b04_03_ai_cache_feedback` | `ai.canonical_answers`, `ai.feedback` | 01 |
| `b04_04_ai_sources` | `ai.content_sources`, `ai.content_chunks` (vector(1024), GIN tsv) | B2 |
| `b04_05_ai_chunks_hnsw` | HNSW index on `ai.content_chunks.embedding` (concurrent, non-transactional) | 04 |
| `b04_06_ai_evals` | `ai.prompt_versions`, `ai.eval_sets`, `ai.eval_runs`, `ai.eval_results` | B1 |
| `b04_07_ai_photo` | `ai.photo_solves` | 01 |
| `b04_08_qbank_ocr_dedupe` | `qbank.import_pages`, `qbank.question_fingerprints`, `qbank.duplicate_candidates` | B2 |
| `b04_09_cms_ai_review` | `cms.ai_review_items` | B2 |
| `b04_10_search_embedding` | Alter `platform.search_documents` add `embedding vector(1024)` (nullable) | B2 |
| `b04_11_search_hnsw` | HNSW index on `platform.search_documents.embedding` (concurrent) | 10 |

### Build 5: live exam engine

| Revision | Creates or alters | Depends |
|---|---|---|
| `b05_01_exam_blueprints` | `exam.section_types` (+ seed CQ, short, MCQ, practical, financial_statement, descriptive), `exam.blueprints`, `exam.blueprint_sections`, `exam.blueprint_rules` | B2 |
| `b05_02_exam_exams` | `exam.exams` (with `registered_count`, `settings`; `status` CHECK includes `voided`), `exam.exam_audiences`, `exam.exam_papers`, `exam.exam_paper_items` | 01, B3 (products) |
| `b05_03_exam_attempts` | `exam.registrations`, `exam.exam_attempts` | 02 |
| `b05_04_exam_answer_log` | `exam.exam_answer_batches` (P, monthly), `exam.exam_answers_latest` (P, monthly); append-only grants on batches | 03 |
| `b05_05_exam_scoring` | `exam.scoring_configs`, `exam.exam_results`, `exam.close_runs`, `exam.late_answer_cases` | 03 |
| `b05_06_exam_merit` | `exam.merit_snapshots`, `exam.merit_entries` | 05 |
| `b05_07_exam_control_room` | `exam.incidents`, `exam.time_extensions` | 02 |

### Build 6: teacher-checked marking, commerce and operations

| Revision | Creates or alters | Depends |
|---|---|---|
| `b06_01_inst_batches` | `institution.teacher_approvals`, `institution.batches`, `institution.batch_members` | B1 |
| `b06_02_inst_tasks` | `institution.written_tasks`, `institution.written_task_items`, `institution.submissions`, `institution.submission_pages` | 01, B2 |
| `b06_03_ai_marking` | `ai.marking_jobs`, `ai.gradings`, `ai.grading_parts`, `ai.accuracy_reports` | 02, B2 |
| `b06_04_commerce_orders` | `commerce.price_points`, `commerce.coupons`, `commerce.orders` | B3 |
| `b06_05_commerce_payments` | `commerce.payments`, `commerce.provider_events`, `commerce.store_purchases` | 04 |
| `b06_06_commerce_refunds_invoices` | `commerce.refunds`, `commerce.invoice_sequences`, `commerce.invoices`, `commerce.credit_notes` | 05 |
| `b06_07_commerce_coupons_referrals` | `commerce.coupon_redemptions`, `commerce.referral_codes`, `commerce.referral_credits` | 04 |
| `b06_08_commerce_reconciliation` | `commerce.reconciliation_runs`, `commerce.reconciliation_exceptions` | 05 |
| `b06_09_ops_content` | `ops.banners`, `ops.notices` | B1 |

### Build 7: P1 personalised learning and engagement

| Revision | Creates or alters | Depends |
|---|---|---|
| `b07_01_curriculum_links` | `curriculum.topic_links` | B2 |
| `b07_02_qbank_families_stats` | `qbank.question_families`; alter `qbank.questions.family_id` add FK (`NOT VALID` + validate); `qbank.item_statistics`, `qbank.item_flags` | B2 |
| `b07_03_qbank_flashcards` | `qbank.flashcard_decks`, `qbank.flashcards` | B2 |
| `b07_04_qbank_current_affairs` | `qbank.current_affairs_items`, `qbank.current_affairs_compilations`; swap CHECK on `qbank.concept_notes.kind` (cheat_sheet, formula_sheet) | B2 |
| `b07_05_cms_p1` | `cms.ai_drafts`, `cms.author_tasks`, `cms.author_payouts` | B2 |
| `b07_06_practice_adaptive` | `practice.ability_estimates`, `practice.review_cards`, `practice.daily_mixes`, `practice.diagnostic_blueprints`, `practice.offline_packs` (no CHECK swap needed: all `practice_sessions.kind` values are listed from B3, 01 §4.E G7-3) | 03 |
| `b07_07_analytics_p1` | `analytics.mastery_state`, `analytics.time_analytics`, `analytics.trend_snapshots`, `analytics.peer_percentiles`, `analytics.readiness_forecasts` | B3 |
| `b07_08_ai_p1` | `ai.ai_items`, `ai.ai_quizzes`, `ai.chapter_summaries`, `ai.coach_plans`, `ai.misconception_clusters` | B4 |
| `b07_09_rewards_badges_leagues` | `rewards.badge_definitions`, `rewards.user_badges`, `rewards.league_tiers` (+ seed), `rewards.leagues`, `rewards.league_members`; add `rewards.streak_days.is_provisional` (expand; S-9) | B3 |
| `b07_10_rewards_challenges_cards` | `rewards.challenges`, `rewards.challenge_progress`, `rewards.share_cards` | B3 |
| `b07_11_notify_study_plan` | `notify.study_plan_items` | 08 |
| `b07_12_community_threads_mentors` | `community.threads`, `community.posts`, `community.post_votes`, `community.mentor_requests`, `community.mentor_replies` | B4 |
| `b07_13_institution_tutor_lock` | add `institution.batches.tutor_mode_lock` (nullable, expand) | B6 |

### Build 8: P1 institutions, parents, exam integrity and growth

| Revision | Creates or alters | Depends |
|---|---|---|
| `b08_01_identity_p1` | `identity.device_profile_links`, `identity.password_credentials`, `identity.email_verifications`, `identity.apple_notifications`; swap CHECK `external_identities.provider` adding `apple` | B1 |
| `b08_02_inst_workspaces` | `institution.workspaces`, `institution.branches`, `institution.workspace_members`; alter `institution.batches` add `workspace_id` FK (nullable) | B6 |
| `b08_03_inst_roster_seats` | `institution.roster_entries`, `institution.roster_imports`, `institution.seat_allocations` | 02 |
| `b08_04_inst_teaching` | `institution.homework_assignments`, `institution.omr_templates`, `institution.omr_scans`, `institution.paper_generations` | 02, B5 |
| `b08_05_parent` | `parent.guardian_links`, `parent.link_codes`, `parent.parent_controls`, `parent.weekly_reports` | B1 |
| `b08_06_exam_integrity` | `exam.integrity_events` (P, monthly), `exam.anomaly_flags`, `exam.attempt_question_orders`, `exam.paper_set_assignments` | B5 |
| `b08_07_exam_written_series` | `exam.written_answers`, `exam.written_answer_pages`, `exam.series`, `exam.series_items`, `exam.series_standings`, `exam.certificates` | B5 |
| `b08_08_notify_tracker` | `notify.tracker_items`, `notify.tracker_follows`, `notify.eligibility_targets`, `notify.eligibility_rules` | B2 |
| `b08_14_notify_email` | `notify.email_messages` (P, monthly); swap CHECK on `notify.templates.channel` adding `email`; add `identity.external_identities.provider_refresh_token_enc` | B1 |
| `b08_09_commerce_subscriptions` | `commerce.subscriptions`, `commerce.proration_quotes`, `commerce.bundles`; alter `commerce.entitlements` and `commerce.orders` add `beneficiary_user_id`; swap CHECK `store_purchases.platform` adding `apple` | B6 |
| `b08_10_commerce_family_affiliates` | `commerce.family_plans`, `commerce.family_members`, `commerce.affiliates`, `commerce.affiliate_attributions`, `commerce.affiliate_payouts` | 09 |
| `b08_11_ops_growth` | `ops.feature_flags`, `ops.campaigns`, `ops.campaign_sends` (P, monthly), `ops.experiments`, `ops.experiment_assignments` | B1 |
| `b08_12_rls_enable` | Expand step: `enable_rls` on the tenant tables (§9) | 02–07 |
| `b08_13_rls_force` | Contract step: `FORCE ROW LEVEL SECURITY`, shipped one release after 12 | 12 |

### Build 9: P2 expansion and scale certification

| Revision | Creates or alters | Depends |
|---|---|---|
| `b09_01_community_groups` | `community.forum_categories`, `community.study_groups`, `community.group_members`, `community.group_messages` (P, monthly) | B7 |
| `b09_02_notify_channels` | `notify.channel_bindings`, `notify.calendar_feeds` | B1 |
| `b09_03_cms_media` | `cms.media_assets` | B2 |
| `b09_04_practice_duels` | `practice.duel_rooms`, `practice.duel_participants`, `practice.duel_rounds`, `practice.duel_answers` | B3 |
| `b09_05_exam_p2` | `exam.proctor_snapshots`, `exam.cutoff_history`, `exam.score_predictions` | B5 |
| `b09_06_analytics_reports` | `analytics.report_exports` | B3 |
| `b09_07_ai_voice` | `ai.voice_sessions`, `ai.voice_turns`, `ai.viva_scenarios` | B4 |
| `b09_08_rewards_store_social` | `rewards.store_items`, `rewards.redemptions`, `rewards.coin_balances`, `rewards.follows`, `rewards.team_leagues`, `rewards.team_scores` | B3 |
| `b09_09_commerce_sponsorship` | `commerce.sponsors`, `commerce.sponsorships`, `commerce.sponsored_seats` | B6 |
| `b09_10_inst_marketplace` | `institution.marketplace_listings`, `institution.payout_accounts`, `institution.payouts`, `institution.whitelabel_configs` | B8 |
| `b09_11_inst_attendance_fees` | `institution.attendance_records`, `institution.fee_records` | B8 |
| `b09_12_parent_alerts` | `parent.alert_rules`, `parent.alert_events` | B8 |

**Totals:** 103 migrations across nine builds, covering all 278 tables listed in `01` §3 (checked by script after the integration additions: `practice.offline_packs`, `notify.email_messages`, `ai.voice_turns` added; `rewards.streak_freeze_events` removed). Columns added during integration (01 §4.D–§4.E) that belong to tables created in B1–B6, such as `qv_content.tenant_id`, `exams.settings`, `questions.is_canary` and `submissions.typed_text`, are created with their tables, so they need no extra migration.

## 4. Seed data versus fixtures

| Kind | Where | Examples | Loaded by |
|---|---|---|---|
| **Reference seeds** (needed in every environment, stable natural keys) | `migrations/seeds/*.csv|json`, applied by the migration that creates the table; later changes ship as new seed migrations (`bNN_MM_seed_<name>_v2`) | Roles, permissions, role-permission map; districts (+ sentinel 0), upazilas; boards; section types; consent documents v1; message templates; moderation terms v1; reward rules v1; quota policies v1; league tiers; runtime config defaults; analytics projection v1 | `helpers/seed.py` upsert by natural key; idempotent |
| **Bulk reference data** (large, refreshed) | Loaded by an admin job from a file in S3, not a migration | Institution list (EIIN), tracks and taxonomy trees, track exam dates | `POST /v1/admin/nodes:import` and the `identity.institutions.import` job |
| **Content** | Never in migrations | Questions, papers, textbooks | CMS imports (QB-07) |
| **Test fixtures** | `tests/factories/` (factory functions, not SQL dumps) | Users, enrolments, a 3-level SSC Physics tree, 20 published MCQs, a CQ with rubric, an exam | Pytest fixtures, inside the rolled-back test transaction |
| **Demo and staging data** | `scripts/seed_staging.py` | One verified SSC Physics chapter (about 150 questions) | Run manually on staging; never in production |

Seeds never contain secrets or personal data. A test asserts that every seeded permission is assigned to at least one role, and that the role list equals AUTH-03's eight roles.

## 5. Expand, migrate, contract

Every migration must work with **both** the previous and the new application version, so an application rollback never needs a schema rollback (v2 §8.3).

| Change | Expand (release N) | Migrate | Contract (release N+1 or later) |
|---|---|---|---|
| Add a value to an enum-like CHECK (e.g. `practice_sessions.kind` adds `daily_mix`) | `swap_check_in` with the superset; old code never writes the new value | — | None needed. Removing a value later requires a contract after a backfill. |
| Add a NOT NULL column (e.g. `daily_activity.rule_version`) | Add the column nullable, with no default rewrite (PG 11+ adds constant defaults without a rewrite, so `DEFAULT 1 NOT NULL` is fine for constants); new code writes it | Backfill job in batches of 10,000 (§6) | `ALTER … SET NOT NULL` after `CHECK (col IS NOT NULL) NOT VALID` + `VALIDATE` (so `SET NOT NULL` skips the full scan) |
| Rename a column (e.g. `marks` → `max_marks`) | Add the new column; new code writes both and reads new-then-old | Backfill | Next release: code reads only the new column. Release after: drop the old one. **Never** `RENAME COLUMN` in place. |
| Rename a table | Avoid. If unavoidable: create a new table, dual-write, backfill, switch reads, drop. | | |
| Add a foreign key | `ADD CONSTRAINT … NOT VALID` | `VALIDATE CONSTRAINT` (takes only `SHARE UPDATE EXCLUSIVE`) | — |
| Add an index on a large table | `create_index_concurrently` in its own non-transactional migration | — | — |
| Drop a column | Code stops reading and writing it (release N) | — | Drop it in release N+1 |
| Change a column type | New column plus backfill plus switch, as for a rename | | |

## 6. Backfill jobs

- Backfills are **job handlers**, not migrations: `jobs/backfill_<name>.py` in the owning module, enqueued by a small migration or an admin command.
- They process keyset batches (`WHERE id > :cursor ORDER BY id LIMIT 10000`), with a short transaction per batch, `pg_sleep(0.05)` between batches, and a cursor stored in the job payload so they can resume.
- They are throttled by the replication-lag and CPU metrics; a backfill pauses when primary CPU > 60%.
- They are idempotent: every write is an upsert or `WHERE col IS NULL`.
- Completion is verified by a count query before the contract migration ships.

## 7. Zero-downtime rules

1. `lock_timeout = 3s` on every migration session (§1). A blocked migration fails fast and is retried.
2. No `ALTER TABLE` that rewrites a large table: no volatile defaults, no type changes in place, no `SET NOT NULL` without a validated CHECK first.
3. Indexes on existing tables use `CREATE INDEX CONCURRENTLY` inside `autocommit_block()`, in a migration that does nothing else. A failed concurrent build leaves an `INVALID` index, which the next run drops and recreates (the helper checks `pg_index.indisvalid`).
4. New tables and their indexes are created normally; they are empty.
5. Constraints are added `NOT VALID`, then validated.
6. Migrations run **before** the new application version starts (a pre-deploy task in ECS). The previous version must keep working against the new schema; CI tests this (§10).
7. Partitioned tables: indexes are created on the parent (PG 11+ propagates them). For a new index on an existing partitioned table, create it `ON ONLY` the parent, then `CONCURRENTLY` on each partition, then `ALTER INDEX … ATTACH PARTITION`. The helper `create_partitioned_index_concurrently` does this.

## 8. Partition maintenance job

- **Job:** `nfr.partition_maintenance`, runs hourly from `workers`, with `dedupe_key = partmaint:{yyyymmddhh}`, using the owner role through a dedicated direct connection.
- **Source of truth:** `app/modules/nfr/internal/partitions.py`, a declarative list of `(table, unit, keep_ahead, retention, archive)`, for example:
  - `("platform.outbox", "day", 3, "7 days", None)`
  - `("exam.exam_answer_batches", "month", 3, "12 months after final", "s3_parquet")`
- **Each run:**
  1. Ensures partitions exist for `now + keep_ahead`.
  2. For expired partitions, verifies the retention condition. For outbox partitions that means every row relayed. For exam partitions it means every exam in them has a final merit snapshot, older than the retention window. Then it archives to S3 Parquet if configured (writing `_SUCCESS` and a row count), then `DETACH PARTITION CONCURRENTLY`, then `DROP TABLE`.
  3. Alerts if any `_default` partition has rows, or if fewer than 2 future partitions exist.
- It never drops a partition whose archive row count does not match the table row count.
- The exam freeze (§11) also applies to this job: no detaches during a freeze window. Creating future partitions is allowed.

## 9. Row-level security in Build 8 (expand then contract)

Tenant tables:

- **Content and exams:** `qbank.questions`, `qbank.question_versions`, `qbank.papers`, `qbank.concept_notes`, `platform.search_documents`, `ai.content_chunks`, `exam.exams`.
- **Institution:** `institution.batches`, `institution.written_tasks`, `institution.submissions`, `institution.homework_assignments`.

The steps:

1. **B2–B7, before RLS.** `tenant_id` exists, and every repository filters by it explicitly (`tenant_id IS NULL OR tenant_id = :tenant`). A test fixture runs every repository query with a tenant set and asserts the filter.
2. **`b08_12_rls_enable` (expand).** Turns on RLS with the policy `USING (tenant_id IS NULL OR tenant_id = current_setting('app.tenant_id', true)::uuid)`. Because the table owner (`app_owner`) bypasses RLS, and `app_rw` is a non-owner, policies apply to the application immediately.
   - The application sets `SET LOCAL app.tenant_id` at the start of every transaction through a SQLAlchemy `after_begin` hook. It is an empty string for platform-only requests, so only platform rows match.
   - Workers that must see all tenants use the role `app_rw_bypass`, which has `BYPASSRLS`, is audited, and is used only by named jobs: indexing, rescoring and backups.
   - This release also ships the cross-tenant read tests.
3. **One release later, `b08_13_rls_force` (contract).** Adds `FORCE ROW LEVEL SECURITY`, so even owner-role sessions are filtered. It ships only after a week of production logs shows no policy-denied queries from legitimate code paths.
4. **Rollback.** Disabling RLS is a single `ALTER TABLE … DISABLE ROW LEVEL SECURITY` migration. The explicit filters from step 1 remain, so isolation never depends on RLS alone.

## 10. CI and testing of migrations

| Check | How | When |
|---|---|---|
| Models match migrations | `alembic check` (fails if autogenerate would produce operations), excluding partitions through `include_object` | Every PR |
| Upgrade from empty | `alembic upgrade head` on a fresh Postgres 17 + pgvector container | Every PR |
| Round trip | `upgrade head → downgrade -1 → upgrade head` for each migration added in the PR | Every PR |
| Upgrade with data | Restore the previous build's tag schema, load the fixture dataset (`scripts/seed_staging.py --small`), then run the new migrations; assert row counts and constraint validity | Every PR touching `migrations/` |
| Previous-app compatibility | Run the previous release's API test suite (tagged image) against the new schema | Release branch |
| Line limit | `scripts/check_file_length.py` covers `migrations/**/*.py` | Pre-commit and CI |
| Revision order | Test that ids follow `bNN_MM_` order and the chain is linear (no branches) | Every PR |
| Registry | `test_registry_matches_migration`: the schemas in `modules/registry.py` equal `b01_01` | Every PR |
| Lock safety lint | A small script fails if a migration contains `ADD COLUMN … DEFAULT <volatile>`, `SET NOT NULL` without a preceding validated CHECK, `CREATE INDEX` without `CONCURRENTLY` on a table from an earlier build, or `RENAME COLUMN` | Every PR |

**Downgrade policy.** Every migration implements `downgrade()` for local development and CI round trips. **Production is forward-only.** A bad migration is fixed by a new forward migration. Downgrades of migrations that drop data (contract steps) raise `NotImplementedError`, with a comment pointing to the restore runbook.

## 11. Exam-freeze rule

No production migrations from **T−24 h to T+2 h** around any live exam with more than 5,000 registrants (v2 §8.3).

- The deploy pipeline reads the exam schedule (`GET /v1/admin/exams?freeze_window=active`) and blocks the `migrate` stage during a freeze.
- An override needs two approvers and is audited.
- The partition maintenance job skips detach and drop during a freeze. Creating future partitions continues.
- Backfill jobs pause automatically during a freeze.

## 12. Deployment sequence per release

1. CI is green (§10) and the release is tagged.
2. A pre-deploy ECS task runs `alembic upgrade head` with the owner role, holding an advisory lock (`pg_advisory_lock(hashtext('alembic'))`) so only one runner applies migrations.
3. Blue/green deploy of the new image (v2 §8.3), with a 10% canary.
4. Post-deploy smoke tests, including `/readyz` on each deployable.
5. Contract migrations for the previous release (if any) ship only in the **next** release, never in the same one as their expand step.

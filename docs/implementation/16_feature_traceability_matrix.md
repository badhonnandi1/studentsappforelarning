# 16 · Feature traceability matrix

**Date:** 2026-11-27 · **Sources:** [`features.md`](../../features.md) v1.0 (180 IDs) · [`system-design-v2.md`](../system-design-v2.md) §9 · tables from [`01_database_design.md`](01_database_design.md) §3 · endpoints from [`14_api_contracts.md`](14_api_contracts.md) §3 · builds from [`04_backend_master_plan.md`](04_backend_master_plan.md) §6.

How to read this matrix:

- **Build** is the *primary* build, where the feature's core is delivered. "+Bn" lists later builds that complete or extend it, and "Bn·" lists earlier builds that lay its foundation.
- Every primary build is counted exactly once in §2.
- Tables are written `schema.table`. Endpoints use the routes in `14` §3, with the `/v1` prefix omitted where it is unambiguous.
- Tests name the planned suites. The build documents (section E) list the exact files.
- Client-only parts are marked **frontend phase (out of scope)**. The nine builds cover the backend only.

**ID count.** There are **180** IDs, the same as `features.md`.

AUTH-01 is shown with five sub-rows (marked ↳), one per sign-in method. Facebook sign-in is a **scope change the user approved on 2026-11-27**: it extends AUTH-01 and does not add a new ID. Sub-rows are excluded from the ID count.

---

## 1. Matrix

### 1.1 Identity & accounts (AUTH)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| AUTH-01 | P0 | Phone OTP, Google, optional email/password (plus Facebook, user-approved) | AUTH | `identity.users`, `identity.otp_challenges`, `identity.external_identities`, `identity.device_sessions`, `identity.refresh_tokens`, `notify.sms_messages` | see sub-rows | NFR-06, PLAN SMS transport, OPS-04 | B1 (+B8) | see sub-rows |
| ↳ AUTH-01 phone OTP | P0 | OTP (+88), hashed, 5 min, 5 tries | AUTH, PLAN | `identity.otp_challenges`, `identity.users`, `notify.sms_messages`, `notify.templates` | `POST /auth/otp/send`, `POST /auth/otp/verify`, `POST /me/phone` | NFR-06 OTP abuse limits | B1 | `tests/modules/auth/api/test_otp.py`, `tests/modules/auth/unit/test_otp_limits.py` |
| ↳ AUTH-01 Google | P0 | Google ID token verification (JWKS, aud, nonce) | AUTH | `identity.external_identities`, `identity.users` | `POST /auth/social/nonce`, `POST /auth/social/{provider}`, `GET/POST/DELETE /me/identities[/{provider}]` | Redis nonce, secret store | B1 | `tests/modules/auth/unit/test_google_provider.py`, `tests/modules/auth/integration/test_social_linking.py` |
| ↳ AUTH-01 Facebook | P0 | Facebook `debug_token` and `/me`; data-deletion and deauthorise callbacks (scope change, 2026-11-27) | AUTH | `identity.external_identities`, `identity.users`, `ops.audit_log` | `POST /auth/social/{provider}`, `POST /webhooks/facebook/data-deletion`, `GET /auth/social/facebook/deletion-status/{code}`, `POST /webhooks/facebook/deauthorize` | Meta app review; age gate 13+ | B1 | `tests/modules/auth/unit/test_facebook_provider.py`, `tests/modules/auth/api/test_facebook_callbacks.py` |
| ↳ AUTH-01 Apple | P0 | Sign in with Apple when iOS ships | AUTH | `identity.external_identities`, `identity.apple_notifications` | `POST /auth/social/{provider}` (apple), `POST /webhooks/apple/notifications` | OFF-04 iOS, Apple guideline 4.8 | B8 | `tests/modules/auth/unit/test_apple_provider.py` |
| ↳ AUTH-01 email/password | P0 (optional) | Deferred per v2 C20 | AUTH | `identity.password_credentials`, `identity.email_verifications` | `POST /auth/password/sign-up`, `/sign-in`, `/reset`, `/reset/confirm`, `POST /auth/email/verify` | Email transport | B8 | `tests/modules/auth/api/test_password_auth.py` |
| AUTH-02 | P0 | Device/session management; single session in live exams | AUTH | `identity.device_sessions` (`exam_epoch`), `identity.refresh_tokens` | `POST /auth/refresh`, `POST /auth/logout`, `GET /me/sessions`, `DELETE /me/sessions/{session_id}` | EXAM-04a takeover (B5) | B1 (+B5) | `tests/modules/auth/integration/test_refresh_rotation.py`, `tests/modules/auth/concurrency/test_token_reuse.py` |
| AUTH-03 | P0 | Eight roles, fine-grained scoped permissions | AUTH | `identity.roles`, `identity.permissions`, `identity.role_permissions`, `identity.role_grants` | `POST /admin/role-grants`, `DELETE /admin/role-grants/{id}`, `GET /me` | OPS-04 audit | B1 | `tests/modules/auth/unit/test_can.py`, `tests/modules/auth/api/test_role_grants.py` |
| AUTH-04 | P0 | Student profile (class, group, version, curriculum, institution, district/upazila, board, exam year) | AUTH | `identity.profiles`, `identity.institutions`, `identity.districts`, `identity.upazilas` | `GET/PUT /me/profile`, `POST /me/profile/photo`, `GET /reference/districts`, `GET /reference/institutions` | COM-05 (photo and name moderation), presigned uploads | B1 | `tests/modules/auth/api/test_profile.py` |
| AUTH-05 | P0 | Multi-track enrolment | AUTH | `identity.track_enrolments` | `GET/POST /me/enrolments`, `PATCH /me/enrolments/{id}` | TAX-01, TAX-03 | B2 | `tests/modules/auth/api/test_enrolments.py` |
| AUTH-06 | P1 | Track promotion with history | AUTH | `identity.track_enrolments` (`promoted_from_id`) | `POST /me/enrolments/{id}:promote` | AUTH-05, ANL projections | B7 | `tests/modules/auth/integration/test_promotion.py` |
| AUTH-07 | P1 | Parent–child linking by code or QR | PAR (data), AUTH | `parent.guardian_links`, `parent.link_codes` | `POST /me/guardian-link-codes`, `POST /guardian/links`, `DELETE /guardian/links/{id}` | NFR-07 consent records | B8 | `tests/modules/par/api/test_linking.py` |
| AUTH-08 | P1 | Several student profiles on a shared device with PIN | AUTH | `identity.device_profile_links`, `identity.device_sessions` | `POST/GET /devices/{device_id}/profiles`, `DELETE /devices/{device_id}/profiles/{user_id}` | AUTH-02 (PIN is client-side: **frontend phase (out of scope)**) | B8 | `tests/modules/auth/api/test_shared_device.py` |
| AUTH-09 | P1 | Institution enrolment by join code, CSV, roll number | INST, AUTH | `institution.roster_entries`, `institution.roster_imports`, `institution.batch_members` | `POST /workspaces/{id}/roster:import`, `POST /workspaces/{id}/roster/invites`, `POST /roster:claim`, `POST /batches:join` | INST-01, INST-02 | B8 | `tests/modules/inst/integration/test_roster_import.py` |
| AUTH-10 | P2 | Under-18 consent dashboard; account deletion and export | AUTH | `identity.guardian_consents`, `identity.data_requests` | `POST/GET /me/data-requests`, `GET /me/data-export/{id}` | NFR-07 (P0 support-driven flow, B6) | B9 (B6·) | `tests/modules/auth/integration/test_data_export.py`, `tests/modules/auth/integration/test_account_deletion.py` |

### 1.2 Curriculum & taxonomy (TAX)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| TAX-01 | P0 | Configurable hierarchy | TAX | `curriculum.tracks`, `curriculum.track_levels`, `curriculum.taxonomy_nodes` | `GET /syllabus-versions/{id}/tree`, `GET /nodes/{node_id}`, `POST/PATCH /admin/nodes[/{id}]` | NFR platform (B1) | B2 | `tests/modules/tax/unit/test_tree_rules.py`, `tests/modules/tax/api/test_tree.py` |
| TAX-02 | P0 | Academic tracks Class 6–12 | TAX | `curriculum.tracks`, `curriculum.syllabus_versions`, `curriculum.taxonomy_nodes` | `GET /tracks`, `POST /admin/nodes:import` | TAX-01; content team trees | B2 | `tests/modules/tax/integration/test_seed_academic.py` |
| TAX-02a | P0 | Admission tracks | TAX | same as TAX-02 | `GET /tracks`, `POST /admin/nodes:import` | TAX-01 | B2 | `tests/modules/tax/integration/test_tree_import.py` |
| TAX-02b | P0 | Job tracks | TAX | same as TAX-02 | `GET /tracks`, `POST /admin/nodes:import` | TAX-01 | B2 | `tests/modules/tax/integration/test_tree_import.py` |
| TAX-03 | P0 | Syllabus versioning by year; one question → several versions | TAX, QB | `curriculum.syllabus_versions`, `curriculum.taxonomy_nodes` (`stable_key`), `qbank.question_node_map` | `GET /tracks/{track_id}/syllabus-versions`, `POST/PATCH /admin/syllabus-versions[/{id}]` | TAX-01 | B2 | `tests/modules/tax/integration/test_copy_forward.py`, `tests/modules/qb/integration/test_multi_syllabus_mapping.py` |
| TAX-04 | P0 | Bangla/English names, ordering, icons, free/paid flag | TAX | `curriculum.taxonomy_nodes` (`name_bn`, `name_en`, `sort`, `icon`, `is_free`) | `GET /syllabus-versions/{id}/tree`, `PATCH /admin/nodes/{id}` | PAY-02 reads `is_free` (B3) | B2 | `tests/modules/tax/api/test_node_admin.py` |
| TAX-05 | P1 | Madrasah and Technical trees | TAX | `curriculum.tracks` (kind madrasah, technical), `curriculum.boards`, `qbank.paper_tracks` | `POST /admin/nodes:import` | TAX-01; shared papers (SSC/Dakhil) | B7 | `tests/modules/tax/integration/test_madrasah_tree.py` |
| TAX-06 | P1 | Cross-track topic links with shared mastery | TAX, ANL | `curriculum.topic_links`, `analytics.mastery_state` | `GET /nodes/{node_id}/links`, `POST/DELETE /admin/topic-links[/{id}]` | ANL-04 | B7 | `tests/modules/tax/api/test_topic_links.py`, `tests/modules/anl/unit/test_linked_mastery.py` |

### 1.3 Question bank (QB)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| QB-01 | P0 | Objective types: MCQ, multi-statement, stimulus | QB | `qbank.questions` (`type`), `qbank.question_versions` (`answer_key`), `qbank.qv_content` | `POST /admin/questions`, `POST /admin/questions/{id}/versions` | TAX-01 | B2 | `tests/modules/qb/unit/test_answer_key_schemas.py` |
| QB-01a | P0 | Written types: CQ (ক/খ/গ/ঘ, variable parts), short, essay | QB | `qbank.cq_subparts`, `qbank.rubric_points` | `POST /admin/questions/{id}/versions` | QB-01 | B2 | `tests/modules/qb/unit/test_cq_subparts.py` |
| QB-01b | P0 | Fill-in, true/false, matching, numeric with tolerance | QB | `qbank.question_versions` (`answer_key`) | `POST /admin/questions` | QB-01 | B2 | `tests/modules/qb/unit/test_answer_key_schemas.py`, `tests/modules/qb/unit/test_numeric_tolerance.py` |
| QB-02 | P0 | Rich content: Unicode, LaTeX, chemistry, tables, images, SVG, audio | QB | `qbank.qv_content` (`rendered_html`), `qbank.question_media`, `qbank.rendering_failures` | `POST /admin/questions/{id}:preview`, `GET /uploads/{purpose}/presign` | KaTeX Node renderer in the worker image | B2 | `tests/modules/qb/integration/test_render_job.py`, `tests/modules/qb/unit/test_bangla_normalise.py` |
| QB-03 | P0 | Metadata: nodes, source, difficulty, Bloom, marks, time, tags, status | QB | `qbank.question_versions`, `qbank.question_node_map` | `POST /admin/questions`, `GET /admin/questions` | TAX | B2 | `tests/modules/qb/api/test_question_metadata.py` |
| QB-04 | P0 | Key, explanation, video URL, linked concept note | QB | `qbank.question_versions` (`video_url`, `concept_note_id`), `qbank.qv_content` (`explanation`), `qbank.concept_notes` | `POST/PATCH /admin/concept-notes[/{id}]`, `GET /concept-notes/{id}` | QB-01 | B2 | `tests/modules/qb/api/test_concept_notes.py` |
| QB-05 | P0 | Paired Bangla/English versions | QB | `qbank.qv_content` (PK `question_version_id, lang`) | `POST /admin/questions/{id}/versions` | QB-06 | B2 | `tests/modules/qb/unit/test_bilingual_pair.py` |
| QB-06 | P0 | Full version history; attempts store version id | QB | `qbank.question_versions` (`supersedes_id`, immutable once published), `cms.workflow_events` | `POST /admin/questions/{id}/versions`, `GET /admin/questions/{id}` | — | B2 | `tests/modules/qb/integration/test_version_immutability.py` |
| QB-07 | P0 | Bulk import Excel/CSV/Word/JSON with validation report | QB | `qbank.import_jobs`, `qbank.import_rows` | `POST /admin/imports`, `GET /admin/imports/{id}`, `POST /admin/imports/{id}:commit` | C22 source rights | B2 | `tests/modules/qb/integration/test_import_xlsx.py`, `tests/modules/qb/unit/test_import_validation.py` |
| QB-07a | P0 | PDF/image import with Bangla + maths OCR, then human review | QB, AI | `qbank.import_jobs`, `qbank.import_pages`, `cms.review_assignments` | `POST /admin/imports`, `GET /admin/imports/{id}/pages` | AI OCR provider (B4) | B4 | `tests/modules/qb/integration/test_ocr_import.py` |
| QB-08 | P0 | Duplicate detection (text, maths, embeddings) | QB | `qbank.question_fingerprints`, `qbank.duplicate_candidates`, `platform.search_documents` (`embedding`) | `GET /admin/duplicates`, `POST /admin/duplicates/{id}:decide` | Embeddings (B4) | B4 | `tests/modules/qb/unit/test_math_canonical.py`, `tests/modules/qb/integration/test_dedupe.py` |
| QB-09 | P0 | Previous-year paper object | QB | `qbank.papers`, `qbank.paper_items`, `qbank.paper_tracks` | `POST/PATCH /admin/papers[/{id}]`, `GET /papers`, `GET /papers/{id}` (B3) | QB-06 | B2 | `tests/modules/qb/api/test_papers.py` |
| QB-10 | P1 | Question families and variants | QB | `qbank.question_families`, `qbank.questions` (`family_id`) | `POST/PATCH /admin/question-families[/{id}]` | QB-06 | B7 | `tests/modules/qb/api/test_families.py` |
| QB-11 | P1 | Item statistics, probable-wrong-key flag | QB, ANL | `qbank.item_statistics`, `qbank.item_flags`, `cms.error_reports` | `GET /questions/{question_version_id}/stats` | NFR-09 S3 log; DuckDB/Athena job | B7 | `tests/modules/qb/integration/test_item_stats_job.py` |
| QB-12 | P1 | Concept notes, cheat and formula sheets | QB | `qbank.concept_notes` (`kind`) | `POST/PATCH /admin/concept-notes[/{id}]`, `GET /concept-notes/{id}` | QB-04 (B2). **Moves to P0 if D1 fails** (risk RK-21) | B7 (B2·) | `tests/modules/qb/api/test_concept_notes.py` |
| QB-13 | P1 | Flashcard decks (auto and user) | QB | `qbank.flashcard_decks`, `qbank.flashcards` | `GET/POST /flashcard-decks`, `POST/PATCH /admin/flashcard-decks[/{id}]` | PRAC-09 | B7 | `tests/modules/qb/api/test_flashcards.py` |
| QB-14 | P1 | Current-affairs feed, quizzes, monthly compilation | QB, AI | `qbank.current_affairs_items`, `qbank.current_affairs_compilations`, `ai.ai_items` | `GET /current-affairs`, `POST/PATCH /admin/current-affairs[/{id}]` | CMS workflow, AI-08 | B7 | `tests/modules/qb/api/test_current_affairs.py` |

### 1.4 CMS

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| CMS-01 | P0 | WYSIWYG editor with live LaTeX, Bangla and mobile preview (backend: preview, autosave) | CMS | `cms.editor_drafts` | `PUT /admin/questions/{id}/draft`, `POST /admin/questions/{id}:preview` | QB-02 renderer; editor UI is **frontend phase (out of scope)** | B2 | `tests/modules/cms/api/test_autosave.py`, `tests/modules/cms/api/test_preview.py` |
| CMS-02 | P0 | Workflow; blind two-person key verification | CMS | `cms.workflow_events`, `cms.key_verifications` (`CHECK verifier_id <> author_id`) | `POST /admin/questions/{id}:submit-review`, `POST /admin/question-versions/{id}/verifications`, `:publish`, `:retire` | QB-06, C22 rights | B2 | `tests/modules/cms/unit/test_workflow_states.py`, `tests/modules/cms/concurrency/test_double_verify.py` |
| CMS-03 | P0 | Role-based access per subject/track; assignment queues | CMS, AUTH | `identity.role_grants`, `cms.review_assignments` | `GET/POST /admin/assignments` | AUTH-03 | B2 | `tests/modules/cms/api/test_scoped_access.py` |
| CMS-04 | P0 | Error-report queue with triage and SLA | CMS | `cms.error_reports` | `GET /admin/error-reports`, `POST /admin/error-reports/{id}:triage`, `POST /questions/{question_id}/error-reports` (B3) | PRAC-07 | B2 (+B3) | `tests/modules/cms/api/test_error_queue.py` |
| CMS-04a | P0 | Error resolution: notify affected users, rescore | CMS, PRAC, EXAM, GAM, PLAN | `cms.corrections`, `practice.score_adjustments`, `exam.scoring_configs`, `exam.merit_snapshots`, `notify.notifications` | `POST /admin/error-reports/{id}:resolve`, `GET /admin/corrections/{id}`, `POST /admin/corrections/{id}:approve-merit` (B5) | PRAC (B3), EXAM (B5) | B3 (+B5 exam part) | `tests/modules/prac/test_rescore_correction.py`, `tests/modules/exam/integration/test_rescoring_exam.py` |
| CMS-05 | P0 | Search and filter by any metadata; bulk edit/tag/move | CMS, NFR | `platform.search_documents`, `qbank.question_versions` | `GET /admin/questions`, `POST /admin/questions:bulk` | NFR-04 lexical (B2), hybrid (B4) | B2 (+B4) | `tests/modules/cms/api/test_bank_search.py`, `tests/modules/cms/api/test_bulk_edit.py` |
| CMS-06 | P0 | Exam blueprint builder (screen; EXAM owns data) | EXAM, CMS | `exam.blueprints`, `exam.blueprint_sections`, `exam.blueprint_rules`, `exam.section_types` | `POST/PATCH /admin/blueprints[/{id}]` | EXAM-01 | B5 | `tests/modules/exam/api/test_blueprints.py` |
| CMS-07 | P1 | AI-assisted authoring with human approval | CMS, AI | `cms.ai_drafts` | `POST /admin/ai-drafts`, `POST /admin/ai-drafts/{id}:decide` | AI gateway (B4) | B7 | `tests/modules/cms/api/test_ai_drafts.py` |
| CMS-08 | P1 | Content coverage dashboard | CMS | reads `qbank.*` through the QB interface (no table) | `GET /admin/reports/coverage` | QB | B7 | `tests/modules/cms/api/test_coverage_report.py` |
| CMS-09 | P1 | Author productivity and payment tracking | CMS | `cms.author_tasks`, `cms.author_payouts` | `GET /admin/reports/authors`, `POST /admin/author-payouts:run` | Integer poisha | B7 | `tests/modules/cms/integration/test_author_payouts.py` |
| CMS-10 | P2 | Media library with CDN, compression, alt text | CMS | `cms.media_assets` | `GET/POST /admin/media` | R2, NFR-11 | B9 | `tests/modules/cms/api/test_media_library.py` |

### 1.5 Practice (PRAC)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| PRAC-01 | P0 | Custom practice builder | PRAC | `practice.practice_sessions` (`filters`), `practice.session_items` | `POST /practice/sessions` | QB published versions, PAY-02 | B3 | `tests/modules/prac/unit/test_builder_filters.py`, `tests/modules/prac/api/test_start_session.py` |
| PRAC-02 | P0 | Learn and Test feedback modes | PRAC | `practice.practice_sessions` (`mode`), `practice.attempt_answers` | `POST /practice/sessions/{id}/answers`, `POST /practice/sessions/{id}:complete` | AI-04 visibility rules | B3 | `tests/modules/prac/api/test_mode_visibility.py` |
| PRAC-03 | P0 | Chapter/topic practice; textbook-exercise mode | PRAC | `practice.practice_sessions` (`kind`, `node_id`) | `POST /practice/sessions`, `GET /home` | TAX, QB source metadata | B3 | `tests/modules/prac/api/test_chapter_session.py` |
| PRAC-04 | P0 | Previous-year paper practice | PRAC, QB | `practice.practice_sessions` (`paper_id`), `qbank.papers` | `GET /papers`, `GET /papers/{id}`, `POST /practice/sessions` | QB-09 | B3 | `tests/modules/prac/api/test_paper_session.py` |
| PRAC-05 | P0 | Mistake Notebook; cleared after two correct in a row | PRAC | `practice.mistake_entries`, `practice.attempt_answers`, `practice.score_adjustments` | `GET /practice/mistakes`, `POST /practice/sessions` (kind mistakes) | Answer transaction | B3 | `tests/modules/prac/unit/test_notebook_rule.py`, `tests/modules/prac/concurrency/test_notebook_two_devices.py` |
| PRAC-06 | P0 | Bookmarks with folders; personal notes | PRAC | `practice.bookmark_folders`, `practice.bookmarks`, `practice.question_notes` | `/practice/bookmark-folders[/{id}]`, `PUT/DELETE /practice/bookmarks/{question_id}`, `GET /practice/bookmarks`, `PUT/DELETE /practice/notes/{question_id}` | — | B3 | `tests/modules/prac/api/test_bookmarks.py`, `tests/modules/prac/api/test_notes.py` |
| PRAC-07 | P0 | "Report error" on every question | PRAC, CMS | `cms.error_reports` | `POST /questions/{question_id}/error-reports` | CMS-04, COM-05 text moderation | B3 | `tests/modules/prac/api/test_report_error.py` |
| PRAC-08 | P1 | Adaptive practice (Elo) at 60–75% success | PRAC | `practice.ability_estimates`, `qbank.item_statistics` | `GET /practice/abilities`, `POST /practice/sessions` (adaptive policy) | QB-11, NFR-09 history | B7 | `tests/modules/prac/unit/test_elo_policy.py` |
| PRAC-09 | P1 | Spaced repetition (FSRS) for mistakes and flashcards | PRAC | `practice.review_cards` | `GET /practice/reviews/due` | QB-13, PRAC-05 | B7 | `tests/modules/prac/unit/test_fsrs.py` |
| PRAC-10 | P1 | Daily Mix | PRAC | `practice.daily_mixes` | `POST /practice/daily-mix` | PRAC-08, PRAC-09, ANL-03 | B7 | `tests/modules/prac/integration/test_daily_mix_unique.py` |
| PRAC-11 | P1 | Speed drill with per-question timer | PRAC, ANL | `practice.practice_sessions` (`kind=speed_drill`), `analytics.time_analytics` | `POST /practice/sessions` | ANL-05 | B7 | `tests/modules/prac/api/test_speed_drill.py` |
| PRAC-12 | P1 | Diagnostic test at onboarding | PRAC | `practice.diagnostic_blueprints`, `practice.ability_estimates` | `POST /practice/diagnostic` | PRAC-08, ANL-04 | B7 | `tests/modules/prac/integration/test_diagnostic_seeding.py` |
| PRAC-13 | P2 | 1v1 duels and group quiz rooms | PRAC | `practice.duel_rooms`, `practice.duel_participants`, `practice.duel_rounds`, `practice.duel_answers` | `POST /duels`, `POST /duels/{code}:join`, `GET /duels/{id}`, `WS /realtime/duels/{id}` | New `realtime` deployable | B9 | `tests/modules/prac/integration/test_duel_room.py`, `tests/entrypoints/realtime/test_ws.py` |

### 1.6 Exam engine (EXAM)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| EXAM-01 | P0 | Blueprint: sections, counts, marks, negative marking, timers, optional sections (N of M), pass marks | EXAM | `exam.blueprints`, `exam.blueprint_sections`, `exam.blueprint_rules`, `exam.section_types` | `POST/PATCH /admin/blueprints[/{id}]` | TAX, QB | B5 | `tests/modules/exam/unit/test_blueprint_validation.py` |
| EXAM-02 | P0 | Exam types: mock, model test, live, past paper, institution/batch (ops-created) | EXAM | `exam.exams` (`kind`), `exam.exam_audiences` | `GET /exams`, `POST/PATCH /admin/exams[/{id}]`, `POST /exams/{id}/practice-attempts` | EXAM-01, QB-09 | B5 | `tests/modules/exam/api/test_exam_types.py` |
| EXAM-03 | P0 | Exam UI support: palette, mark-for-review, OMR view, timer, auto-submit, calculator flag | EXAM | `exam.exam_attempts`, `exam.blueprints` (`calculator_allowed`) | `GET /exams/{id}/attempts/current/status`, `POST /exam-attempts/{id}:submit` | UI is **frontend phase (out of scope)** | B5 | `tests/modules/exam/api/test_attempt_status.py` |
| EXAM-04 | P0 | Before start: listing, registration, fee, reminders, countdown, locked paper | EXAM, PAY, PLAN | `exam.registrations`, `exam.exam_papers`, `exam.exams` | `GET /exams/{id}`, `POST /exams/{id}/registrations`, `POST /admin/exams/{id}:freeze-paper` | PAY-02 (fees via orders in B6), PLAN-02 | B5 (+B6 paid fees) | `tests/modules/exam/integration/test_registration.py`, `tests/modules/exam/integration/test_paper_freeze.py` |
| EXAM-04a | P0 | Synchronised start, late entry, auto-submit, publish and unlock times | EXAM, edge | `exam.exams`, `exam.exam_attempts`, `exam.close_runs` | `POST /exams/{id}/attempts:start`, `GET /edge/time`, `GET /edge/exams/{id}/key` | AUTH-02 epoch, edge Worker | B5 | `tests/modules/exam/integration/test_two_phase_close.py`, `edge/test/key_release.test.ts` |
| EXAM-05 | P0 | Answer persistence, resume, server timer | EXAM | `exam.exam_answer_batches`, `exam.exam_answers_latest`, `exam.late_answer_cases` | `POST /ingest/attempts/{attempt_id}/batches`, `GET /exams/{id}/attempts/current/acknowledged` | SQS, NFR-03 | B5 | `tests/modules/exam/integration/test_contiguity.py`, `tests/entrypoints/exam_ingest/test_no_postgres.py`, `tests/load/exam_fault_injection.js` (k6) |
| EXAM-06 | P0 | Merit lists, tie-breaks, publish/unpublish, download | EXAM | `exam.merit_snapshots`, `exam.merit_entries` | `POST /admin/exams/{id}/merit-snapshots`, `POST /admin/merit-snapshots/{id}:publish`, `GET /admin/merit-snapshots/{id}/export`, `GET /exams/{id}/merit` | C15 self-reported label, NFR-07 | B5 | `tests/modules/exam/unit/test_tie_break.py`, `tests/modules/exam/integration/test_merit_replay_identical.py` |
| EXAM-07 | P0 | Result page: score, counts, negative loss, time, rank, percentile, topper/average, solutions | EXAM | `exam.exam_results`, `exam.merit_entries` | `GET /exam-attempts/{id}/result`, `GET /exam-attempts/{id}/review` | Redis precompute | B5 | `tests/modules/exam/api/test_result_payload.py` |
| EXAM-08 | P0 | Re-attempt (practice only) and review mode | EXAM, PRAC | `exam.exam_attempts` (`attempt_no`, `kind`), `practice.attempt_answers` | `POST /exam-attempts/{id}:reattempt`, `GET /exam-attempts/{id}/review` | PRAC mastery feed | B5 | `tests/modules/exam/integration/test_reattempt_not_ranked.py` |
| EXAM-09 | P1 | Paper anti-cheat: shuffle, variants, single device | EXAM | `exam.attempt_question_orders`, `exam.paper_set_assignments`, `exam.exam_papers` (`set_code`) | `POST /exams/{id}/attempts:start` (variant-aware) | QB-10 (B7) | B8 | `tests/modules/exam/unit/test_shuffle_seed.py` |
| EXAM-09a | P1 | Device anti-cheat logs; FLAG_SECURE (client) | EXAM | `exam.integrity_events` | `POST /exam-attempts/{id}/integrity-events` | FLAG_SECURE is **frontend phase (out of scope)** | B8 | `tests/modules/exam/api/test_integrity_events.py` |
| EXAM-09b | P1 | Anomaly and collusion detection, review console | EXAM | `exam.anomaly_flags` | `GET /admin/exams/{id}/anomalies`, `POST /admin/anomalies/{id}:decide` | NFR-09 S3 log | B8 | `tests/modules/exam/integration/test_similarity_job.py` |
| EXAM-10 | P1 | Written exam uploads graded by AI and/or human | EXAM, AI | `exam.written_answers`, `exam.written_answer_pages`, `ai.gradings`, `ai.grading_parts` | `POST /exam-attempts/{id}/written-answers/{qv_id}/pages` | AI-07 (B6) | B8 | `tests/modules/exam/integration/test_written_exam_grading.py` |
| EXAM-11 | P1 | Exam series with cumulative leaderboard | EXAM, PAY | `exam.series`, `exam.series_items`, `exam.series_standings` | `GET /exam-series`, `GET /exam-series/{id}/standings`, `POST/PATCH /admin/exam-series[/{id}]` | PAY products | B8 | `tests/modules/exam/integration/test_series_standings.py` |
| EXAM-12 | P1 | Certificates with verification QR | EXAM | `exam.certificates` | `GET /certificates`, `GET /certificates/verify/{code}` | EXAM-06, EXAM-11 | B8 | `tests/modules/exam/api/test_certificate_verify.py` |
| EXAM-13 | P2 | Score predictor from historical cut-offs | EXAM | `exam.cutoff_history`, `exam.score_predictions` | `GET /predictions`, `POST /admin/cutoffs:import` | ANL history | B9 | `tests/modules/exam/unit/test_predictor.py` |
| EXAM-14 | P2 | Proctored mode snapshots | EXAM | `exam.proctor_snapshots` | `POST /exam-attempts/{id}/proctor-snapshots` | AUTH-10 consent (face = sensitive data) | B9 | `tests/modules/exam/api/test_proctor_consent.py` |

### 1.7 Analytics (ANL)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| ANL-01 | P0 | Dashboard: readiness, accuracy tree, attempts, study time, streak | ANL | `analytics.topic_progress`, `analytics.daily_study`, `analytics.projection_versions` | `GET /progress/dashboard` | Answer transaction, EXAM blueprint weights (readiness), GAM streak | B3 | `tests/modules/anl/unit/test_readiness.py`, `tests/modules/anl/integration/test_progress_projection.py` |
| ANL-02 | P0 | Exam history with score and rank trends | ANL, EXAM | `exam.exam_results`, `exam.merit_entries` (read through EXAM interface) | `GET /progress/exam-history` | EXAM-06 | B5 | `tests/modules/anl/api/test_exam_history.py` |
| ANL-03 | P0 | Weak-area list with one-tap practice | ANL, PRAC | `analytics.topic_progress` | `GET /progress/weak-areas`, `POST /practice/sessions` (kind weak_topic) | ANL-01 | B3 | `tests/modules/anl/unit/test_weak_areas_min_attempts.py` |
| ANL-04 | P1 | Mastery map | ANL | `analytics.mastery_state` | `GET /progress/mastery` | PRAC-08, TAX-06 | B7 | `tests/modules/anl/unit/test_mastery_levels.py` |
| ANL-05 | P1 | Time analytics, guess detection, negative-mark loss | ANL | `analytics.time_analytics` | `GET /progress/time-analytics` | NFR-09 | B7 | `tests/modules/anl/integration/test_time_analytics_job.py` |
| ANL-06 | P1 | Previous-year trend analytics | ANL | `analytics.trend_snapshots` | `GET /progress/trends` | QB-03 sources, QB-09 | B7 | `tests/modules/anl/integration/test_trend_job.py` |
| ANL-07 | P1 | Peer percentile | ANL | `analytics.peer_percentiles` | `GET /progress/percentile` | S3 log query | B7 | `tests/modules/anl/unit/test_percentile_lookup.py` |
| ANL-08 | P1 | Readiness forecast | ANL | `analytics.readiness_forecasts` | `GET /progress/forecast` | ANL-01, `curriculum.track_exam_dates` | B7 | `tests/modules/anl/unit/test_forecast.py` |
| ANL-09 | P2 | Exportable progress PDF | ANL | `analytics.report_exports` | `POST /progress/reports`, `GET /progress/reports/{id}` | PAR, INST | B9 | `tests/modules/anl/integration/test_report_pdf.py` |

### 1.8 AI tutor (AI)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| AI-01 | P0 | Chat tutor (BN/EN/Banglish), context-aware, history, new chat per subject | AI | `ai.tutor_threads`, `ai.tutor_messages`, `ai.ai_usage` | `GET/POST /tutor/threads`, `GET /tutor/threads/{id}/messages`, `DELETE /tutor/threads/{id}`, `POST /tutor/messages` | PRAC context (mistakes), AUTH profile | B4 | `tests/modules/ai/integration/test_tutor_message_flow.py`, `tests/modules/ai/api/test_sse_stream.py` |
| AI-02 | P0 | Grounded answers (RAG) over textbooks, bank, explanations, notes | AI | `ai.content_sources`, `ai.content_chunks`, `platform.search_documents` | `POST /tutor/messages`, `POST/PATCH /admin/ai/sources[/{id}]` | D1 (textbook licence), QB | B4 | `tests/modules/ai/integration/test_retrieval_permissions.py` |
| AI-02a | P0 | Citations on every answer; "not sure" otherwise | AI | `ai.tutor_citations` | `POST /tutor/messages` (final event) | AI-02 | B4 | `tests/modules/ai/unit/test_citation_verifier.py` |
| AI-03 | P0 | Photo solve: OCR, steps, concept, 3 similar questions | AI | `ai.photo_solves`, `ai.tutor_messages` | `POST /photo-solves`, `GET /photo-solves/{id}`, `POST /photo-solves/{id}:confirm`, `POST /photo-solves/{id}/practice` | OCR provider, SymPy sandbox, NFR-04 | B4 | `tests/modules/ai/integration/test_photo_solve.py`, `tests/modules/ai/unit/test_sympy_check.py` |
| AI-04 | P0 | Explain actions on every question | AI | `ai.canonical_answers`, `ai.tutor_messages` | `POST /tutor/messages` (`action`) | QB verified explanations; C5 cache | B4 | `tests/modules/ai/integration/test_canonical_cache_privacy.py` |
| AI-05 | P0 | Guardrails: education-only, child-safe moderation, disabled in live exams | AI, COM, EXAM | `community.moderation_decisions`, Redis `exam_lock:{user_id}` | `POST /tutor/messages` (423 `locked_exam`) | EXAM lock writer (B5), COM-05 | B4 (+B5) | `tests/modules/ai/unit/test_exam_lock_fail_closed.py`, `tests/modules/ai/eval/test_safety_set.py` |
| AI-05a | P0 | Quotas, rate limits, feedback, flagged answers to review queue | AI, PAY, CMS | `ai.feedback`, `cms.ai_review_items`, `commerce.quota_policies` | `POST /tutor/messages/{id}/feedback`, `GET /tutor/quota`, `GET /admin/ai-review-items`, `POST /admin/ai-review-items/{id}:resolve` | PAY-02 | B4 | `tests/modules/ai/concurrency/test_quota_charged_once.py`, `tests/modules/ai/api/test_feedback.py` |
| AI-06 | P1 | Socratic/direct modes; parent/teacher mode lock | AI, PAR | `ai.tutor_threads` (`mode`, `mode_locked_by`), `parent.parent_controls` | `PUT /tutor/threads/{id}/mode` | PAR-03 (B8) lock source | B7 (+B8) | `tests/modules/ai/api/test_mode_lock.py` |
| AI-07 | P0 | Written-answer grader input (typed or photographed) | AI, INST | `institution.submissions`, `institution.submission_pages`, `ai.marking_jobs` | `POST /tasks/{task_id}/submissions`, `POST /submissions/{id}/pages`, `POST /submissions/{id}:submit` | INST-02a, NFR-07 consent, QB-01a rubrics | B6 | `tests/modules/ai/integration/test_marking_pipeline.py` |
| AI-07a | P0 | Grader rubrics (CQ at launch) | AI, QB | `qbank.cq_subparts`, `qbank.rubric_points` | `POST /admin/questions/{id}/versions` (rubrics) | QB-01a | B6 (B2·) | `tests/modules/ai/unit/test_rubric_prompt_build.py` |
| AI-07b | P0 | Grader output: score, breakdown, missing points, model answer, rewrites | AI | `ai.gradings`, `ai.grading_parts` (`missing_points`, `rewrite_suggestions`, `model_answer_ref`) | `GET /submissions/{id}` | AI-07 | B6 | `tests/modules/ai/unit/test_grading_output_schema.py` |
| AI-07c | P0 | Teacher review queue; teacher mark is final | AI, INST | `ai.gradings` (`source=teacher`, `is_final`), `ai.marking_jobs` (`triage_priority`) | `GET /teacher/review-queue`, `GET /teacher/submissions/{id}`, `POST /teacher/submissions/{id}/marks`, `POST /teacher/tasks/{id}:release` | AI-07 | B6 | `tests/modules/inst/api/test_teacher_isolation.py`, `tests/modules/ai/integration/test_teacher_final.py` |
| AI-07d | P0 | Published marking accuracy per subject and part | AI | `ai.accuracy_reports`, `ai.eval_runs` | `GET /marking/accuracy`, `POST /admin/marking/accuracy-reports` | §4.10 gate (QWK) | B6 | `tests/modules/ai/unit/test_qwk.py` |
| AI-08 | P1 | Quiz generator, items labelled "AI", kept apart | AI | `ai.ai_items`, `ai.ai_quizzes` | `POST /ai/quizzes` | AI-02 | B7 | `tests/modules/ai/integration/test_ai_quiz_isolated.py` |
| AI-09 | P1 | Chapter summariser | AI | `ai.chapter_summaries` | `GET /ai/summaries/{chapter_node_id}`, `POST /admin/ai/summaries/{id}:review` | AI-02 | B7 | `tests/modules/ai/api/test_summaries.py` |
| AI-10 | P1 | AI study coach | AI, PLAN | `ai.coach_plans`, `notify.study_plan_items` | `POST /ai/coach/plan` | PLAN-03, ANL-04 | B7 | `tests/modules/ai/integration/test_coach_replan.py` |
| AI-11 | P1 | Mistake diagnosis into misconception clusters | AI | `ai.misconception_clusters` | `GET /ai/misconceptions` | PRAC history, QB-11 | B7 | `tests/modules/ai/integration/test_misconceptions.py` |
| AI-12 | P2 | Voice: Bangla STT, TTS | AI | `ai.voice_sessions` | `POST /ai/voice/transcribe`, `POST /ai/voice/speak` | Speech eval | B9 | `tests/modules/ai/api/test_voice.py` |
| AI-13 | P2 | Spoken English partner | AI | `ai.voice_sessions` | `POST /ai/spoken-english/sessions` | AI-12 | B9 | `tests/modules/ai/api/test_spoken_english.py` |
| AI-14 | P2 | Viva/interview simulator | AI | `ai.voice_sessions`, `ai.viva_scenarios` | `POST /ai/viva/sessions` | AI-12 | B9 | `tests/modules/ai/api/test_viva.py` |
| AI-15 | P0 | Router, cache, per-user cost tracking | AI | `ai.ai_usage`, `ai.canonical_answers`, `ai.cost_budgets` | `GET /admin/ai/usage`, `POST /admin/ai/canonical-answers/{id}:correct` | Free-form semantic cache deferred to P1 (C5) | B4 | `tests/modules/ai/unit/test_router_tiers.py`, `tests/modules/ai/unit/test_budget_breaker.py` |
| AI-15a | P0 | Prompt versioning, offline eval per subject | AI | `ai.prompt_versions`, `ai.eval_sets`, `ai.eval_runs`, `ai.eval_results` | `GET /admin/ai/evals` | CI eval subset | B4 | `tests/modules/ai/eval/test_eval_gate.py` |

### 1.9 Gamification (GAM)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| GAM-01 | P0 | XP for activities, levels, daily goal | GAM | `rewards.reward_rules`, `rewards.reward_transactions`, `rewards.user_totals`, `rewards.daily_activity`, `rewards.board_flags` | `GET /rewards/summary`, `PUT /rewards/daily-goal`, `GET /rewards/history`, `POST /admin/gam/rules` | Answer transaction (PRAC) | B3 | `tests/modules/gam/unit/test_xp_rules.py`, `tests/modules/gam/concurrency/test_daily_cap.py`, `tests/modules/gam/integration/test_replay_no_double_xp.py` |
| GAM-02 | P0 | Daily streak with freeze | GAM | `rewards.streak_state`, `rewards.streak_days` | `GET /rewards/summary` | Effective time (§5.3 v2), settlement job | B3 | `tests/modules/gam/unit/test_streak_scenarios.py` (§5.5 + 20 clock cases), `tests/modules/gam/concurrency/test_settlement_race.py` |
| GAM-03 | P0 | Leaderboards: period × audience × track | GAM | Redis `lb:*`, `rewards.leaderboard_snapshots`, `rewards.friend_codes`, `rewards.friend_links`, `identity.privacy_settings` | `GET /leaderboards`, `GET/POST /friends`, `GET /friends/code`, `DELETE /friends/{user_id}`, `POST /admin/gam/boards:rebuild`, `GET /admin/gam/flags` | NFR-07 privacy, AUTH-04 institution/district | B3 | `tests/modules/gam/integration/test_board_rebuild.py`, `tests/modules/gam/api/test_board_privacy.py` |
| GAM-04 | P1 | Badges (rules engine) | GAM | `rewards.badge_definitions`, `rewards.user_badges` | `GET /badges`, `POST/PATCH /admin/gam/badges[/{code}]` | Events | B7 | `tests/modules/gam/unit/test_badge_rules.py` |
| GAM-05 | P1 | Weekly leagues with promotion/relegation | GAM | `rewards.leagues`, `rewards.league_members`, `rewards.league_tiers` | `GET /leagues/current` | GAM-03 weekly board | B7 | `tests/modules/gam/integration/test_league_rollover.py` |
| GAM-06 | P1 | Challenges with time window and rewards | GAM | `rewards.challenges`, `rewards.challenge_progress` | `GET /challenges`, `POST /challenges/{id}:join`, `POST/PATCH /admin/gam/challenges[/{id}]` | Events | B7 | `tests/modules/gam/integration/test_challenge_progress.py` |
| GAM-07 | P1 | Share cards with referral link | GAM, PAY | `rewards.share_cards`, `commerce.referral_codes` | `POST /share-cards` | PAY-04 referral | B7 | `tests/modules/gam/api/test_share_card_minor_privacy.py` |
| GAM-08 | P2 | Rewards store (coins) | GAM, PAY | `rewards.store_items`, `rewards.redemptions`, `rewards.coin_balances` | `GET /store/items`, `POST /store/redemptions` | PAY grants (AI credits) | B9 | `tests/modules/gam/concurrency/test_coin_spend.py` |
| GAM-09 | P2 | Follows; institution team leagues | GAM | `rewards.follows`, `rewards.team_leagues`, `rewards.team_scores` | `POST/DELETE /follows/{user_id}`, `GET /team-leagues/current` | GAM-03 | B9 | `tests/modules/gam/integration/test_team_scores.py` |

### 1.10 Planner & alerts (PLAN)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| PLAN-01 | P0 | Exam countdown per track | PLAN | `curriculum.track_exam_dates` (read through TAX) | `GET /countdowns` | AUTH-05 | B3 | `tests/modules/plan/api/test_countdowns.py` |
| PLAN-02 | P0 | Notification centre + push (FCM; APNs in B8) | PLAN | `notify.notifications`, `notify.deliveries`, `notify.push_tokens`, `notify.preferences`, `notify.templates` | `GET /notifications`, `POST /notifications:mark-read`, `POST/DELETE /push-tokens[/{id}]`, `GET/PUT /notification-preferences`, `POST/PATCH /admin/templates[/{code}]` | Events from all modules; quiet hours (NFR-07) | B3 | `tests/modules/plan/integration/test_fanout_dedupe.py`, `tests/modules/plan/unit/test_quiet_hours.py` |
| PLAN-03 | P1 | Study routine/calendar | PLAN | `notify.study_plan_items` | `/study-plan/items[/{id}]` | AI-10 | B7 | `tests/modules/plan/api/test_study_plan.py` |
| PLAN-04 | P1 | Circular and exam-date tracker | PLAN | `notify.tracker_items` | `GET /tracker`, `POST/PATCH /admin/tracker[/{id}]` | OPS admin | B8 | `tests/modules/plan/api/test_tracker.py` |
| PLAN-04a | P1 | Tracker follow and alert | PLAN | `notify.tracker_follows` | `PUT/DELETE /tracker/{item_id}/follow` | PLAN-04, PLAN-02 | B8 | `tests/modules/plan/integration/test_tracker_alerts.py` |
| PLAN-05 | P1 | Eligibility checker | PLAN | `notify.eligibility_targets`, `notify.eligibility_rules` | `POST /eligibility:check`, `POST/PATCH /admin/eligibility-rules[/{id}]` | AUTH-04 | B8 | `tests/modules/plan/unit/test_eligibility_rules.py` |
| PLAN-06 | P1 | Bangla SMS channel for critical alerts | PLAN | `notify.sms_messages`, `notify.templates` | (channel used by PLAN-02 sends) | SMS transport (B1) | B8 (B1·) | `tests/modules/plan/integration/test_sms_alerts.py` |
| PLAN-07 | P2 | WhatsApp/Telegram; Google Calendar export | PLAN | `notify.channel_bindings`, `notify.calendar_feeds` | `POST/DELETE /channels/{channel}`, `POST /calendar-feed`, `GET /calendar-feed/{token}.ics` | PLAN-03 | B9 | `tests/modules/plan/api/test_ical_feed.py` |

### 1.11 Community (COM)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| COM-01 | P1 | Per-question threads, upvotes, pinned teacher answers | COM | `community.threads`, `community.posts`, `community.post_votes` | `GET /questions/{question_id}/thread`, `POST /threads/{thread_id}/posts`, `POST /posts/{post_id}/vote`, `POST /posts/{post_id}:pin` | COM-05 | B7 | `tests/modules/com/api/test_threads.py` |
| COM-02 | P1 | Paid mentor escalation with SLA | COM, PAY | `community.mentor_requests`, `community.mentor_replies` | `POST /mentor-requests`, `GET /mentor-requests/{id}`, `GET /mentor/queue`, `POST /mentor/requests/{id}/replies` | PAY product, AI handoff | B7 | `tests/modules/com/integration/test_mentor_sla.py` |
| COM-03 | P2 | Subject Q&A forum | COM | `community.forum_categories`, `community.threads` (`scope=forum`) | `GET/POST /forums/{category_id}/threads` | COM-01 | B9 | `tests/modules/com/api/test_forum.py` |
| COM-04 | P2 | Study groups with minor-safety controls | COM | `community.study_groups`, `community.group_members`, `community.group_messages` | `GET/POST /study-groups`, `POST /study-groups/{id}/members`, `GET/POST /study-groups/{id}/messages` | AUTH-10 consent | B9 | `tests/modules/com/unit/test_minor_safety.py` |
| COM-05 | P0 | Moderation: profanity filter, report, mute, ban, audit | COM | `community.moderation_terms`, `community.moderation_decisions`, `community.content_reports`, `community.user_restrictions` | `POST /reports`, `/admin/moderation/*` | OPS-04 audit | B1 | `tests/modules/com/unit/test_moderate_banglish.py`, `tests/modules/com/api/test_restrictions.py` |

### 1.12 Parent portal (PAR)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| PAR-01 | P1 | Child overview | PAR, ANL | `parent.guardian_links`; reads ANL, GAM and EXAM through their interfaces | `GET /guardian/children`, `GET /guardian/children/{child_id}/overview` | AUTH-07 | B8 | `tests/modules/par/api/test_overview_access.py` |
| PAR-02 | P1 | Weekly report via app and Bangla SMS | PAR, PLAN | `parent.weekly_reports`, `notify.sms_messages` | `GET /guardian/children/{child_id}/reports` | PLAN-06 | B8 | `tests/modules/par/integration/test_weekly_report_job.py` |
| PAR-03 | P1 | Controls: tutor mode lock, time cap, quiet hours | PAR | `parent.parent_controls`, `notify.preferences` | `GET/PUT /guardian/children/{child_id}/controls` | AI-06, PLAN-02 | B8 | `tests/modules/par/integration/test_controls_enforced.py` |
| PAR-04 | P1 | Pay for a child; family plan | PAY, PAR | `commerce.orders` (`beneficiary_user_id`), `commerce.entitlements` (`beneficiary_user_id`), `commerce.family_plans`, `commerce.family_members` | `POST /orders`, `POST /family-plans`, `POST /family-plans/{id}/members` | PAY-03 | B8 | `tests/modules/pay/integration/test_beneficiary_entitlement.py` |
| PAR-05 | P2 | Alerts ("no study for 3 days", "score dropped") | PAR | `parent.alert_rules`, `parent.alert_events` | `GET/POST/DELETE /guardian/children/{child_id}/alerts[/{id}]` | ANL, PLAN | B9 | `tests/modules/par/integration/test_alert_dedupe.py` |

### 1.13 Institution (INST)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| INST-01 | P1 | Workspace: branding, branches, teachers, batches | INST | `institution.workspaces`, `institution.branches`, `institution.workspace_members`, `institution.batches` | `POST /admin/workspaces`, `GET/PATCH /workspaces/{id}`, `/workspaces/{id}/branches`, `/workspaces/{id}/members`, `POST /workspaces/{id}/batches` | RLS (tenant) | B8 | `tests/modules/inst/integration/test_rls_cross_tenant.py` |
| INST-02 | P1 | Roster management; seats | INST, PAY | `institution.roster_entries`, `institution.roster_imports`, `institution.seat_allocations`, `commerce.entitlements` (`source=institution_seat`) | `POST /workspaces/{id}/roster:import`, `GET/POST /workspaces/{id}/seats` | AUTH-09 | B8 | `tests/modules/inst/concurrency/test_seat_overallocation.py` |
| INST-02a | P0 | Minimal teacher batch: approval, join code, written task, collect answers | INST | `institution.teacher_approvals`, `institution.batches`, `institution.batch_members`, `institution.written_tasks`, `institution.written_task_items`, `institution.submissions`, `institution.submission_pages` | `POST /teacher/applications`, `/admin/teacher-applications*`, `/teacher/batches*`, `POST /batches:join`, `POST /batches/{id}:leave`, `POST /teacher/batches/{id}/tasks`, `GET /batches/{id}/tasks` | NFR-07 consent, AI-07 | B6 | `tests/modules/inst/api/test_join_requires_consent.py`, `tests/modules/inst/api/test_batch_isolation.py` |
| INST-03 | P1 | Exams from platform and private bank | INST, QB, EXAM | `qbank.questions` (`tenant_id`), `exam.exams` (`tenant_id`) | `POST/PATCH /workspaces/{id}/questions[/{qid}]`, `POST /workspaces/{id}/exams` | RLS, tenant-filtered search and caches | B8 | `tests/modules/inst/integration/test_private_bank_isolation.py` |
| INST-04 | P1 | Batch exam scheduling with batch merit | INST, EXAM | `exam.exams`, `exam.exam_audiences`, `exam.merit_snapshots` | `POST /workspaces/{id}/exams`, `GET /workspaces/{id}/exams/{eid}/merit` | EXAM (B5) | B8 | `tests/modules/inst/integration/test_batch_merit.py` |
| INST-05 | P1 | Mobile OMR scanning | INST | `institution.omr_templates`, `institution.omr_scans` | `POST /workspaces/{id}/omr-templates`, `POST /workspaces/{id}/omr-scans` | On-device scan is **frontend phase (out of scope)** | B8 | `tests/modules/inst/integration/test_omr_sync.py` |
| INST-06 | P1 | Question paper generator (Bangla typesetting, sets A–D) | INST | `institution.paper_generations` | `POST /workspaces/{id}/paper-generations` | PDF renderer with Bangla fonts | B8 | `tests/modules/inst/integration/test_paper_pdf.py` |
| INST-07 | P1 | Analytics per batch and student | INST, ANL | reads `analytics.*` with tenant filter (no table) | `GET /workspaces/{id}/analytics` | ANL | B8 | `tests/modules/inst/api/test_batch_analytics.py` |
| INST-08 | P1 | Assignments with due dates; AI-assisted grading with override | INST, AI | `institution.homework_assignments`, `institution.written_tasks`, `ai.gradings` | `POST /workspaces/{id}/homework`, `GET /me/homework` | AI-07 | B8 | `tests/modules/inst/api/test_homework.py` |
| INST-09 | P2 | Teacher marketplace with revenue share and payouts | INST, PAY | `institution.marketplace_listings`, `institution.payout_accounts`, `institution.payouts` | `/workspaces/{id}/listings*`, `GET /marketplace`, `GET/PUT /workspaces/{id}/payout-account` | PAY | B9 | `tests/modules/inst/integration/test_payout_calc.py` |
| INST-10 | P2 | White-label subdomain or app | INST | `institution.whitelabel_configs` | `GET/PUT /workspaces/{id}/whitelabel`, `GET /whitelabel/{subdomain}/config` | App builds are **frontend phase (out of scope)** | B9 | `tests/modules/inst/api/test_whitelabel_config.py` |
| INST-11 | P2 | Attendance and basic fee tracking | INST | `institution.attendance_records`, `institution.fee_records` | `POST /workspaces/{id}/attendance`, `GET/POST /workspaces/{id}/fees` | INST-02 | B9 | `tests/modules/inst/api/test_attendance.py` |

### 1.14 Commerce (PAY)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| PAY-01 | P0 | Product catalogue; validity in days or until exam date | PAY | `commerce.products`, `commerce.product_grants`, `commerce.price_points` (B6) | `GET /products`, `POST/PATCH /admin/products[/{id}]` | TAX exam dates | B3 | `tests/modules/pay/unit/test_validity_calc.py` |
| PAY-02 | P0 | Entitlement engine; free quotas; trials | PAY | `commerce.entitlements`, `commerce.entitlement_events`, `commerce.quota_policies`, Redis `quota:*` | `GET /me/entitlements`, `POST /me/trials`, `POST/PATCH /admin/quota-policies[/{id}]` | — | B3 | `tests/modules/pay/unit/test_entitlement_union.py`, `tests/modules/pay/integration/test_quota_rebuild.py` |
| PAY-03 | P0 | bKash, aggregator (Nagad, Rocket, Upay, cards), Play Billing; Apple IAP with iOS | PAY | `commerce.orders`, `commerce.payments`, `commerce.provider_events`, `commerce.store_purchases` | `POST /orders`, `GET /orders/{id}`, `POST /orders/{id}/callback`, `POST /store/purchases/google`, `POST /webhooks/bkash`, `/aggregator`, `/google-play` | D2, merchant accounts | B6 (+B8 Apple) | `tests/modules/pay/integration/test_bkash_execute_once.py`, `tests/modules/pay/concurrency/test_double_capture.py` |
| PAY-04 | P0 | Coupons, referral credits, invoices/receipts (PDF, SMS) | PAY | `commerce.coupons`, `commerce.coupon_redemptions`, `commerce.referral_codes`, `commerce.referral_credits`, `commerce.invoices`, `commerce.invoice_sequences` | `POST /coupons:validate`, `GET /me/referral`, `GET /me/invoices`, `GET /me/invoices/{id}/pdf`, `/admin/coupons*` | PLAN SMS | B6 | `tests/modules/pay/concurrency/test_coupon_limit.py`, `tests/modules/pay/unit/test_invoice_numbering.py` |
| PAY-05 | P0 | Refunds, reconciliation, webhook retries, failed-payment recovery | PAY | `commerce.refunds`, `commerce.credit_notes`, `commerce.reconciliation_runs`, `commerce.reconciliation_exceptions` | `POST /admin/payments/{id}/refunds`, `GET /admin/reconciliation/runs`, `POST /admin/reconciliation/uploads`, `POST /admin/reconciliation/exceptions/{id}:resolve` | Provider report APIs **[Needs evidence]** | B6 | `tests/modules/pay/integration/test_partial_refund_union.py`, `tests/modules/pay/integration/test_reconciliation_mismatch.py`, `tests/modules/pay/integration/test_missing_webhook_sweeper.py` |
| PAY-06 | P1 | Auto-renew, family plan, bundles, proration | PAY | `commerce.subscriptions`, `commerce.family_plans`, `commerce.family_members`, `commerce.bundles`, `commerce.proration_quotes` | `GET/POST/DELETE /me/subscriptions[/{id}]`, `POST /me/subscriptions/{id}:change` | Tokenised gateways | B8 | `tests/modules/pay/unit/test_proration.py` |
| PAY-07 | P1 | Affiliate/ambassador program | PAY | `commerce.affiliates`, `commerce.affiliate_attributions`, `commerce.affiliate_payouts` | `POST /affiliates`, `GET /affiliates/me/report`, `POST /admin/affiliate-payouts:run` | PAY-04 | B8 | `tests/modules/pay/integration/test_affiliate_attribution.py` |
| PAY-08 | P2 | Scholarships and sponsored seats | PAY | `commerce.sponsors`, `commerce.sponsorships`, `commerce.sponsored_seats` | `POST/PATCH /admin/sponsorships[/{id}]`, `POST /admin/sponsorships/{id}/seats` | PAY-02 (`source=scholarship`) | B9 | `tests/modules/pay/concurrency/test_sponsored_seat_limit.py` |

### 1.15 Offline & device (OFF)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| OFF-01 | P0 | Android app and PWA. Backend part: minimum app version, compressed payloads, session bundles under 30 KB. App is **frontend phase (out of scope)**. | NFR, PRAC | `platform.runtime_config` (min version) | `GET /config/client`; `X-Min-App-Version` header; `426 upgrade_required` | §6.6 v2 client gates (frontend) | B3 (B1·) | `tests/core/test_min_app_version.py`, `tests/modules/prac/api/test_session_payload_budget.py` |
| OFF-02 | P0 | Lite mode. Backend part: lite payloads without image bytes. Client is **frontend phase (out of scope)**. | PRAC, NFR | `qbank.question_media` | `X-Lite-Mode` on content endpoints | OFF-01 | B3 | `tests/modules/prac/api/test_lite_mode_payload.py` |
| OFF-03 | P1 | Offline practice packs. Backend part: encrypted pack build, entitlement-bound expiry, 72 h effective-time window. Client sync is **frontend phase (out of scope)**. | PRAC, PAY | `practice.attempt_answers`, `commerce.entitlements` | `POST /practice/answers:sync` (pack mode) | GAM effective-time window | B7 | `tests/modules/prac/integration/test_offline_pack_sync.py` |
| OFF-04 | P1 | iOS. Backend part: APNs, Apple IAP, Sign in with Apple. App is **frontend phase (out of scope)**. | PLAN, PAY, AUTH | `notify.push_tokens` (`platform=apns`), `commerce.store_purchases`, `identity.external_identities` | `POST /store/purchases/apple`, `POST /webhooks/apple-store`, `POST /webhooks/apple/notifications` | AUTH-01 Apple | B8 | `tests/modules/pay/integration/test_apple_iap.py`, `tests/modules/plan/integration/test_apns.py` |
| OFF-05 | P2 | Desktop web exam mode. **No backend work:** it uses the B5 and B8 exam APIs. The client is **frontend phase (out of scope)**. | — | — | Existing exam endpoints | EXAM, INST-04 | B9 | `tests/contract/test_exam_api_desktop_compat.py` |

### 1.16 Ops & admin (OPS)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| OPS-01 | P0 | Admin console: users, subscriptions, manual grants, refunds (backend APIs; console on an admin framework) | OPS, AUTH, PAY | reads through AUTH and PAY interfaces; `ops.audit_log` | `GET /admin/users`, `GET /admin/users/{id}`, `POST /admin/users/{id}:suspend`, `GET /admin/orders`, `POST /admin/entitlements`, `POST /admin/entitlements/{id}:revoke`, `POST /admin/payments/{id}/refunds` | PAY-05, OPS-04 | B6 | `tests/modules/ops/api/test_admin_console_audited.py` |
| OPS-01a | P0 | Live-exam control room | EXAM, OPS | `exam.incidents`, `exam.time_extensions`, `exam.scoring_configs`, `exam.close_runs` | `GET /admin/exams/{id}/control-room`, `POST /admin/exams/{id}:extend`, `POST /admin/exams/{id}/questions/{qv_id}:invalidate`, `/admin/exams/{id}/incidents*`, `/admin/exams/{id}/late-answers*` | EXAM-05 | B5 | `tests/modules/exam/integration/test_extend_time_propagates.py`, `tests/modules/exam/integration/test_invalidate_rescore.py` |
| OPS-02 | P0 | Support ticketing, FAQ, call/WhatsApp links (helpdesk bought, C19) | OPS | `platform.runtime_config` (support links) | `GET /support/config`, `POST /support/widget-token` | Vendor **[Needs evidence]** | B6 | `tests/modules/ops/api/test_support_widget_token.py` |
| OPS-03 | P0 | Banners, announcements, notices (blog and SEO on a static site, C19) | OPS | `ops.banners`, `ops.notices` | `GET /banners`, `GET /notices`, `/admin/banners*`, `/admin/notices*` | — | B6 | `tests/modules/ops/api/test_banner_audience.py` |
| OPS-04 | P0 | Audit logs for all admin actions | OPS | `ops.audit_log` | `GET /admin/audit-log` | — | B1 | `tests/modules/ops/integration/test_audited_wrapper.py`, `tests/modules/ops/db/test_audit_append_only.py` |
| OPS-05 | P1 | Segmented campaigns; A/B tests | OPS, PLAN | `ops.campaigns`, `ops.campaign_sends`, `ops.experiments`, `ops.experiment_assignments` | `/admin/campaigns*`, `POST /admin/campaigns/{id}:send`, `/admin/experiments*` | PLAN-02, PLAN-06 | B8 | `tests/modules/ops/integration/test_campaign_quiet_hours.py` |
| OPS-06 | P1 | Business analytics | OPS, ANL | S3 Parquet event log (no table) | `GET /admin/bi/{report}` | NFR-09 | B8 | `tests/modules/ops/integration/test_bi_queries.py` |
| OPS-07 | P1 | Feature flags and remote config | OPS | `ops.feature_flags`, `platform.runtime_config` | `GET/PUT /admin/feature-flags[/{key}]`, `GET /config/client` | Kill switches (B1) | B8 (B1·) | `tests/modules/ops/unit/test_flag_targeting.py` |

### 1.17 Platform & non-functional (NFR)

| Feature ID | Pri | Feature | Module | Database Tables | API Endpoints | Dependencies | Build | Tests |
|---|---|---|---|---|---|---|---|---|
| NFR-01 | P0 | 200k concurrent live-exam target; load-tested before every major exam | EXAM, NFR | `exam.*` | `/ingest/*`, `/edge/*` | Launch cap 20k (C17) | B5 (+B9 250k rehearsal) | `tests/load/exam_20k.py`, `tests/load/exam_250k.py` (B9) |
| NFR-01a | P0 | Pre-generated papers on CDN, queued submissions, batch rank | EXAM | `exam.exam_papers`, `exam.merit_snapshots` | `POST /admin/exams/{id}:freeze-paper`, `GET /edge/exams/{id}/key` | R2, SQS | B5 | `tests/modules/exam/integration/test_bundle_no_keys.py` |
| NFR-02 | P0 | Question load under 300 ms on 3G; result under 5 s | PRAC, EXAM | `exam.exam_results`, Redis `exam:result:*` | `POST /practice/sessions`, `GET /exam-attempts/{id}/result` | Session bundles (B3), provisional score (B5) | B5 (B3· practice gates) | `tests/load/practice_session_start.py`, `tests/load/result_publish_rush.py` |
| NFR-03 | P0 | 99.9%; zero-loss answers; AI down ≠ practice down | NFR, EXAM, AI | `exam.close_runs`, `ai.pending_questions` | `/readyz` | Contiguity check, circuit breakers | B5 (+B4 AI degradation, +B6 SLO alerting) | `tests/modules/exam/integration/test_contiguity.py`, `tests/modules/ai/integration/test_provider_outage_fallback.py`, `tests/contract/test_practice_without_ai.py` |
| NFR-04 | P0 | Bangla-aware full-text, spelling variants, Banglish, maths and vector search | NFR | `platform.search_documents` | `GET /admin/questions` (B2), `GET /search/questions` (B4) | bge-m3 embeddings (B4) | B4 (B2· lexical) | `tests/modules/nfr/unit/test_bangla_fold.py`, `tests/modules/nfr/unit/test_math_canonical_search.py`, `tests/modules/nfr/eval/test_search_gate_500.py` |
| NFR-05 | P0 | Full BN/EN localisation, Bangla numerals and dates. Backend part: bilingual templates and content, numeral formatting. UI is **frontend phase (out of scope)**. | NFR, PLAN | `notify.templates`, `qbank.qv_content` | `Accept-Language` on all endpoints | — | B1 (+B2 content) | `tests/shared/test_bangla_numerals.py`, `tests/modules/plan/unit/test_template_render.py` |
| NFR-06 | P0 | OWASP Top 10, rate limiting, OTP abuse, encrypted PII | NFR, AUTH | `identity.users` (`*_enc`, `*_hash`), `identity.otp_challenges` | All endpoints (tiers §1.7 of `14`) | KMS | B1 (+B6 pen-test readiness) | `tests/core/test_ratelimit.py`, `tests/core/test_pii_crypto.py`, `tests/security/test_bola_matrix.py` |
| NFR-06a | P0 | Signed content URLs; scraping detection | NFR, QB | `qbank.question_media`, Redis `crawl:*` | `GET /uploads/{purpose}/presign`; T-content tier | Canary questions (B6) | B2 (+B6 crawl detection, canaries) | `tests/modules/qb/api/test_signed_media.py`, `tests/modules/nfr/integration/test_crawl_detection.py` |
| NFR-07 | P0 | Minors' privacy: first name and institution only, opt-out, no phones, consent, retention | AUTH, GAM, EXAM | `identity.guardian_consents`, `identity.privacy_settings`, `identity.consent_documents`, `identity.data_requests` (B6) | `POST /me/consent/guardian/start`, `/confirm`, `GET/PUT /me/privacy` | D4 legal | B1 (+B3 boards, +B5 merit, +B6 data requests) | `tests/modules/auth/api/test_guardian_consent.py`, `tests/modules/gam/api/test_board_privacy.py` |
| NFR-08 | P0 | Crash/ANR, APM, structured logs, alerting, live-exam dashboards (crash/ANR is client) | NFR | — (metrics and logs) | `/livez`, `/readyz`, control room | OpenTelemetry | B6 (B1· foundation, B5· exam dashboards) | `tests/core/test_logging_redaction.py`, `tests/core/test_request_id.py` |
| NFR-09 | P0 | Event pipeline from day one | NFR | `platform.outbox`, `platform.jobs`, `platform.processed_events`, `platform.relay_checkpoints` | `POST /events:batch` (B3) | S3 Parquet | B1 (+B3 answer events, telemetry) | `tests/modules/nfr/concurrency/test_job_skip_locked.py`, `tests/modules/nfr/integration/test_outbox_relay_exactly_once.py` |
| NFR-10 | P1 | Multi-region backups, PITR, DR runbook (pulled forward as a v2 §8.2 gate) | NFR | — (RDS and S3 configuration) | — | Terraform | B6 | Restore drill record; `tests/ops/restore_drill_checklist.md` |
| NFR-11 | P1 | Accessibility. Backend part: alt text and labels in payloads. UI is **frontend phase (out of scope)**. | QB, CMS | `qbank.question_media` (`alt_text_bn`, `alt_text_en`) | `QuestionPayload.media[].alt` | CMS-10 | B8 | `tests/modules/qb/api/test_alt_text_required.py` |

---

## 2. Reconciliation

### 2.1 By module (must equal `features.md` summary)

| Module | P0 | P1 | P2 | Total |
|---|---|---|---|---|
| AUTH | 5 | 4 | 1 | 10 |
| TAX | 6 | 2 | 0 | 8 |
| QB | 12 | 5 | 0 | 17 |
| CMS | 7 | 3 | 1 | 11 |
| PRAC | 7 | 5 | 1 | 13 |
| EXAM | 9 | 6 | 2 | 17 |
| ANL | 3 | 5 | 1 | 9 |
| AI | 14 | 5 | 3 | 22 |
| GAM | 3 | 4 | 2 | 9 |
| PLAN | 2 | 5 | 1 | 8 |
| COM | 1 | 2 | 2 | 5 |
| PAR | 0 | 4 | 1 | 5 |
| INST | 1 | 8 | 3 | 12 |
| PAY | 5 | 2 | 1 | 8 |
| OFF | 2 | 2 | 1 | 5 |
| OPS | 5 | 3 | 0 | 8 |
| NFR | 11 | 2 | 0 | 13 |
| **Total** | **93** | **67** | **20** | **180** |

### 2.2 By primary build

| Build | P0 | P1 | P2 | Total | IDs |
|---|---|---|---|---|---|
| B1 | 10 | 0 | 0 | 10 | AUTH-01–04, COM-05, OPS-04, NFR-05, NFR-06, NFR-07, NFR-09 |
| B2 | 23 | 0 | 0 | 23 | AUTH-05, TAX-01, 02, 02a, 02b, 03, 04, QB-01, 01a, 01b, 02–07, 09, CMS-01–05, NFR-06a |
| B3 | 19 | 0 | 0 | 19 | PRAC-01–07, GAM-01–03, ANL-01, ANL-03, PAY-01, PAY-02, PLAN-01, PLAN-02, CMS-04a, OFF-01, OFF-02 |
| B4 | 12 | 0 | 0 | 12 | AI-01, 02, 02a, 03, 04, 05, 05a, 15, 15a, QB-07a, QB-08, NFR-04 |
| B5 | 16 | 0 | 0 | 16 | EXAM-01, 02, 03, 04, 04a, 05, 06, 07, 08, CMS-06, OPS-01a, ANL-02, NFR-01, NFR-01a, NFR-02, NFR-03 |
| B6 | 13 | 1 | 0 | 14 | AI-07, 07a, 07b, 07c, 07d, INST-02a, PAY-03, 04, 05, OPS-01, 02, 03, NFR-08, NFR-10 (P1) |
| B7 | 0 | 34 | 0 | 34 | AUTH-06, TAX-05, 06, QB-10–14, CMS-07–09, PRAC-08–12, ANL-04–08, AI-06, AI-08–11, GAM-04–07, PLAN-03, COM-01, 02, OFF-03 |
| B8 | 0 | 32 | 0 | 32 | AUTH-07, 08, 09, EXAM-09, 09a, 09b, 10, 11, 12, PLAN-04, 04a, 05, 06, PAR-01–04, INST-01, 02, 03–08, PAY-06, 07, OFF-04, OPS-05–07, NFR-11 |
| B9 | 0 | 0 | 20 | 20 | All P2 IDs |
| **Total** | **93** | **67** | **20** | **180** | |

**P0 is complete at the end of B6.** The only priority moved earlier is NFR-10 (P1), into B6, because v2 §8.2 makes a restore drill a launch gate. No P0 item is deferred past B6. The parts of P0 features that land in later builds are all optional or client-gated: Apple and email/password under AUTH-01 (B8), and Apple IAP under PAY-03 (B8).

---

## 3. Cross-check findings

Found while building the matrix against `features.md`, v2 §9, `01` §3 and `14` §3. Items marked **Action** must be applied to the named document before its build starts. They are listed here so the independent review (`00` Part B) can close them.

### 3.1 Missing features

None. All 180 IDs map to a primary build and to at least one table or endpoint, or to an explicit "no backend work" statement (OFF-05). The §6 automated check confirms this.

### 3.2 Missing entities or endpoints

| # | Gap | Feature | Action |
|---|---|---|---|
| G1 | AI-07 accepts a **typed** answer. `institution.submissions` has only pages. | AI-07 | Add `typed_text text NULL` to `institution.submissions` (01 §3.15, B6). |
| G2 | There is no endpoint for a **practice estimate** on a self-practised CQ answer outside a batch (v2 §4.10 "practice estimate" for subjects that pass the higher gate). | AI-07, AI-07b | Add `POST /v1/practice/answers/{answer_id}/marking` (B6, T-ai, Idem R) to 14 §3.8. `ai.gradings.submission_ref_type = 'practice_answer'` already supports it. |
| G3 | There is no registry of **canary questions** (NFR-06a leak tracing). | NFR-06a | Add `qbank.questions.is_canary boolean DEFAULT false`, and record canary-to-user exposure in the event log (B6). |
| G4 | Crawl detection has no throttle restriction kind. | NFR-06a | Extend `community.user_restrictions.kind` with `content_throttle` (B6). |
| G5 | There is no endpoint to **add cards to a user deck**. | QB-13 | Add `POST /v1/flashcard-decks/{id}/cards` (B7). |
| G6 | There is no endpoint to **record a flashcard review grade**. Mistake reviews use sessions; flashcards do not. | PRAC-09 | Add `POST /v1/practice/reviews/{card_id}` (B7). |
| G7 | The AUTH-10 consent dashboard has no view or withdraw endpoint. | AUTH-10 | Add `GET /v1/me/consents` and `POST /v1/me/consents/{id}:withdraw` (B9). |
| G8 | Paid live-exam registration (EXAM-04 fee) needs orders, which arrive only in B6. | EXAM-04 | B5 supports free and entitlement-gated exams. The fee path is wired in B6. This is already reflected in the Build column. |

### 3.3 Circular dependencies

None remain. Three potential cycles were checked and resolved by direction rules (`04` §4):

| Pair | Risk | Resolution |
|---|---|---|
| AI ↔ EXAM | AI needs the exam lock, and EXAM never needs AI. | AI reads `exam.is_user_exam_locked()`; EXAM writes the Redis key. One direction only. |
| PRAC ↔ CMS | PRAC creates error reports through CMS, and CMS-04a rescoring changes PRAC data. | CMS records the correction and publishes `correction.created`. The PRAC job `prac.rescore_correction` (and EXAM's rescore in B5) consumes it, writes its own adjustments, and publishes `rescoring.progress` and `rescoring.completed`. CMS consumes those to advance `cms.corrections`. CMS never imports PRAC, ANL or GAM (R-03). |
| INST ↔ AI | INST shows gradings, and AI drafts from INST submissions. | INST publishes `submission.submitted`, with page keys, version id and tenant, and calls AI's public API to read and record marks. AI never imports INST. |

### 3.4 Duplicate functionality

| Item | Verdict |
|---|---|
| `analytics.daily_study` vs `rewards.daily_activity` | **Justified.** They have different owners and purposes. ANL tracks per-enrolment study time for display; GAM keeps an account-wide rules row, with the atomic XP cap and goal. Merging them would make GAM depend on ANL rows inside its savepoint. |
| `rewards.streak_freeze_events` vs ledger kind `freeze` | **Resolved:** dropped; freezes are read from `rewards.reward_transactions` and `rewards.streak_state`. |
| `rewards.user_totals.coins` vs `rewards.coin_balances` | **Resolved:** `coin_balances` kept (B9, `CHECK (coins >= 0)` for spends); `user_totals` has no coin column. |
| `platform.runtime_config` vs `ops.feature_flags` | **Justified layering.** Kill switches must exist at P0 with no targeting logic; flags extend them in B8. `GET /config/client` merges both. |
| `qbank.question_media` vs `cms.media_assets` | **Justified.** Version-pinned media vs a reusable library (B9). Library assets are referenced from versions, never copied back. |
| Exam answers copied into `practice.attempt_answers` | **Justified.** Mastery and the notebook read one record (v2 "one attempt record feeds everything"). The copy happens after final scoring, not on the ingest path. |

### 3.5 Architectural inconsistencies

| # | Inconsistency | Action |
|---|---|---|
| I1 | `14` uses relationship checks labelled `Role:` (`Role:mentor`, `Role:affiliate`, `Role:guardian`, `Role:room.member`, `Role:group.member`, `Role:link.party`). AUTH-03 has exactly eight roles. | Interpret these as **relationship authorization** (link, membership or ownership checks in the owning module), or as permissions granted through `identity.role_grants` scopes: mentor = Teacher role + `mentor` scope; affiliate = Student + `affiliate` scope. State this in `14` §1.2. |
| I2 | The plan mentioned "15 schemas"; `01` §2 lists 16 (one per server module). | `01` is authoritative: 16. |
| I3 | v2 §8.2 gate "A replayed answer id from another user is rejected" cannot be enforced with `(user_id, id)` uniqueness on a user-partitioned table. | Restated as "never returns another user's data" (`00`, risk RK-29). |
| I4 | NFR-10 is P1 in `features.md`, but a restore drill is a v2 P0 gate. | Delivered in B6, with priority unchanged in the matrix. |

### 3.6 Security gaps noted

- `GET /v1/certificates/verify/{code}` is public. It must return first name and institution only for minors (NFR-07), never full name or phone.
- `GET /v1/auth/social/facebook/deletion-status/{code}` is public. The code must be at least 128-bit random, with no user data beyond the status.
- `GET /v1/reference/institutions` is public and scrapeable. The data has low sensitivity; keep it behind the T-read limit.
- Typed and handwritten answers sent to the marker are untrusted input. Prompt-injection flags are required (v2 §4.10), and G1 adds typed text to that surface.
- Tenant isolation exists only as filters until B8 adds RLS. Each build from B2 must include the cross-tenant read test with `tenant_id` filters.

### 3.7 High-risk modules

EXAM (B5), AI (B4, B6), NFR (B1, B5), PAY (B6), GAM correctness (B3), and INST tenancy (B8). See `20_risk_register.md`.

### 3.8 Critical-path dependencies

The critical path is B1 → B2 → B3 → B5 → B6.

Inside builds:

- Outbox and job queue (B1) → answer events (B3)
- Published versions with `render_status` and `index_status` = done (B2) → session start (B3)
- Answer transaction (B3) → tutor context (B4) and exam re-attempts feeding mastery (B5)
- AI provider layer (B4) → marking drafts (B6)
- Exam lock contract (B4) → lock writer (B5)

### 3.9 Unnecessary implementation complexity

- `rewards.streak_freeze_events`: dropped. `rewards.coin_balances`: kept, and `user_totals.coins` was not added (resolved in 01 §4.B).
- `analytics.time_analytics` could be computed on read at P1 volume. Keep the table only if the endpoint p95 exceeds budget.
- `commerce.proration_quotes` (B8) is needed only if PAY-06 upgrades are offered on a gateway that supports tokenisation. Defer the table until a gateway qualifies.

---

## 4. How this matrix is checked

1. **ID completeness.** A script extracts every `| <ID> | <Pri> |` row from `features.md` §1–17 and from §1 of this file. Sub-rows starting `| ↳` are skipped. It compares the two sets of IDs and the priority per ID. Pass: 180 IDs, identical sets, identical priorities.
2. **Build assignment.** Every main row has a `Build` cell starting with `B1`–`B9`. The §2.2 counts are recomputed from the Build column.
3. **Table names.** Every backticked `schema.table` in the matrix must appear in `01` §3, with Redis keys excluded.
4. **Endpoints.** Every route in the matrix must appear in `14` §3, after normalising the `/v1` prefix.
5. **When it runs.** Steps 3–4 run in CI from Build 1 as `scripts/check_traceability.py`, a docs check with no database. They re-run whenever `01`, `14`, `16` or `features.md` changes.

### 4.1 Result of the check run on 2026-11-27

The check ran as a one-off script in the session scratchpad (Python, read-only over the four documents). It will become `scripts/check_traceability.py` in Build 1.

```
features.md IDs: 180   matrix IDs: 180   duplicates: none
missing: none   extra: none   priority mismatches: none
per primary build: B1 10, B2 23, B3 19, B4 12, B5 16, B6 14, B7 34, B8 32, B9 20  (= 180)
per build/priority: B1–B5 all P0; B6 13 P0 + 1 P1; B7 34 P1; B8 32 P1; B9 20 P2
tables referenced: 272, all present in 01 §3
routes referenced: 332; 3 differ only in bracket notation from 14
  (/admin/nodes/{id} ≡ /admin/nodes[/{id}]; /me/identities[/{provider}]; /push-tokens[/{id}]), none missing
```

**Result: pass, 180/180 with matching priorities.** The gaps G1–G7 in §3.2 are new endpoints and columns that must be added to `01` and `14`. They were not counted as failures, because the matrix references only rows that already exist.

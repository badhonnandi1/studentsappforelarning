# Build 2 · Curriculum, question bank & content workflow

| Item | Value |
|---|---|
| Status | Planned · not started |
| Depends on | Build 1 merged and its exit criteria met ([05_build_01.md](05_build_01.md) §F.6) |
| Estimated effort | 10–14 backend person-weeks ([04 §6.3](04_backend_master_plan.md)) |
| Feature IDs | P0: TAX-01, TAX-02, TAX-02a, TAX-02b, TAX-03, TAX-04, AUTH-05, QB-01, QB-01a, QB-01b, QB-02, QB-03, QB-04, QB-05, QB-06, QB-07, QB-09, CMS-01, CMS-02, CMS-03, CMS-04 (queue and triage), CMS-05. Partial: NFR-04 (lexical search), NFR-06a (signed media URLs), NFR-05 (bilingual content). |
| Next build | [07_build_03.md](07_build_03.md) |

---

## 0. How to run this build

**Read first:**
1. [`README.md`](README.md).
2. [`04_backend_master_plan.md`](04_backend_master_plan.md).
3. This document.
4. [`01_database_design.md`](01_database_design.md): §1, §3.1 (`search_documents`), §3.2 (`track_enrolments`), §3.6, §3.7 (the B2 rows), §3.8 (the B2 rows), §5.1, §5.2 (R7, R8).
5. [`14_api_contracts.md`](14_api_contracts.md): the B2 rows in §3.2, §3.4 and §3.5.
6. [`system-design-v2.md`](../system-design-v2.md): §3.1 and §7.1. [`market-validation.md`](../market-validation.md) §2.1 (section and CQ structures).

**Preconditions:** `main` contains Build 1, and `scripts/check.sh` is green on `main`. Staging runs Build 1.

**Branch:** `build/02-content`

**Commands:**
```bash
cd backend && uv sync && docker compose up -d
uv run alembic upgrade head
scripts/check.sh
uv run pytest -m "not load"
docker compose run --rm worker-node node --version   # KaTeX renderer image check (C.9)
```

**Stop rule.** Stop when §F holds and the PR is open. Do not build practice sessions (Build 3) or anything in the AI module.

---

## A. Overview

| Item | Detail |
|---|---|
| Name | Curriculum, question bank & content workflow |
| Objective | Curriculum trees for every track as data. Immutable, bilingual, versioned questions of all P0 types with rubrics. Previous-year papers. Structured bulk import with a validation report. Server-side maths rendering. The full CMS workflow with blind two-person key verification and assignment queues. Error-report triage. A Bangla-aware lexical search over the bank. |
| Business value | The content team can load, tag, verify and publish the pilot track (SSC 2028 Physics plus one humanities subject, about 15,000 questions). Verification is the largest schedule risk ([architecture-review.md](../architecture-review.md) §4.3), so the tooling must exist early. |
| Technical value | Gives PRAC, EXAM and AI a stable contract: `qb.get_versions(ids)` returning immutable published versions with rendered HTML and no answer keys unless asked. |
| Modules | TAX (`curriculum`), QB (`qbank`), CMS (`cms`), AUTH (enrolments), NFR (`search_documents`) |
| Dependencies | B1: auth, RBAC, audit, jobs, outbox, storage presign, moderation, `shared.bangla_text` |
| Complexity | 4/5 |
| Effort | 10–14 pw |

**Features**

| ID | Scope in this build |
|---|---|
| TAX-01 | Configurable hierarchy through `track_levels` and `taxonomy_nodes` with `ltree` paths |
| TAX-02 / 02a / 02b | Academic, admission and job tracks as seed data (trees authored by curriculum experts; the code supports any depth) |
| TAX-03 | Syllabus version per track and year; copy-forward; `stable_key` links "the same chapter" across years; one question mapped to nodes in several versions |
| TAX-04 | Bangla and English names, order, icons and the free/paid flag on every node |
| AUTH-05 | `track_enrolments`: several per account; enrolment carries the syllabus version |
| QB-01 / 01a / 01b | All ten types with typed answer-key validation: MCQ single, multi-statement MCQ, stimulus MCQ, CQ (variable subparts), short answer, essay, fill-in, true/false, matching, numeric with tolerance |
| QB-02 | Unicode and LaTeX bodies; tables; images, SVG and audio as `question_media`; KaTeX rendered to HTML at publish |
| QB-03 | Metadata columns: nodes, source, author and computed difficulty, Bloom level, marks, time estimate, tags, status |
| QB-04 | Answer key, explanation, video URL, linked concept note |
| QB-05 | Bangla and English content of one version in `qv_content` (one key, one identity) |
| QB-06 | Immutable versions; an edit creates a new version; `supersedes_id`; past attempts keep their version id |
| QB-07 | Excel, CSV, Word and JSON import with a row-level validation report; creates drafts |
| QB-09 | Papers that pin versions; board, year and unit; `paper_tracks` for shared papers |
| CMS-01 | Backend for the WYSIWYG editor: autosaved drafts, preview rendering (KaTeX, Bangla), mobile-preview HTML |
| CMS-02 | Workflow Draft → In Review → Verified → Published → Retired; blind two-person key verification; tie-break by a third person |
| CMS-03 | Role scopes per subject and track; assignment queues for authors and reviewers |
| CMS-04 | Error-report queue with triage SLA (24 h) and resolution SLA (72 h) timers. Student submission (PRAC-07) and correction rescoring (CMS-04a) come in B3. |
| CMS-05 | Search and filter by any metadata; bulk edit, tag, move |
| NFR-04 (lexical) | Normalisation, phonetic folding, Banglish romanisation, maths canonical tokens, trigram. Vectors and fusion come in B4. |
| NFR-06a (part) | Media only through short-lived signed URLs |

**Risks and blockers**

| Risk | Mitigation |
|---|---|
| KaTeX is JavaScript | A Node 20 CLI (`tools/katex-render/`, ~80 lines of JS, pinned `katex` version) runs in the worker image. Python calls it as a subprocess with a JSON batch. The CLI's output is snapshot-tested. |
| Real bank format unknown | Import mappers are per format, with column-mapping profiles stored in the import job's `totals.mapping`. The week-1 bank inventory gives samples for fixtures. |
| Word (.docx) parsing quality | Accept a documented template only (styles for stem, options, answer, explanation); anything else is reported row by row. |
| Trees for all tracks are content work | The code is generic. Seed only the pilot tracks plus skeletons (top two levels) of all TAX-02, 02a and 02b tracks. |
| Editor complexity (CMS-01) | The backend exposes drafts and preview only. The editor UI is frontend work after Build 9. |

---

## B. Database implementation

### B.1 Tables to create

| Schema | Tables | 01 ref |
|---|---|---|
| `curriculum` | `tracks`, `track_levels`, `syllabus_versions`, `taxonomy_nodes`, `track_exam_dates`, `boards` | §3.6 |
| `identity` | `track_enrolments` | §3.2 |
| `qbank` | `questions`, `question_versions`, `qv_content`, `cq_subparts`, `rubric_points`, `question_node_map`, `question_media`, `papers`, `paper_items`, `paper_tracks`, `concept_notes`, `import_jobs`, `import_rows`, `rendering_failures` | §3.7 |
| `cms` | `workflow_events`, `key_verifications`, `review_assignments`, `editor_drafts`, `error_reports` | §3.8 |
| `platform` | `search_documents` (without `embedding`; B4 adds it) | §3.1 |

**Tables to modify:**
- `identity.profiles`: add an FK from `board_code` to `curriculum.boards(code)` (expand migration; B1 stored `board_code` as text).
- `identity.permissions`: seed the new permission codes `content.exam` and `curriculum` if they are missing, plus `content.read`, `content.author`, `content.verify`, `content.publish`, `content.triage` and `content.lead` (already seeded in B1; verify).

### B.2 Relationships, indexes and constraints

**Curriculum**
- `syllabus_versions.track_id` → `tracks`; uq `(track_id, year)`.
- `taxonomy_nodes.syllabus_version_id` → `syllabus_versions`; `parent_id` → `taxonomy_nodes` (same version, enforced by trigger-free service validation plus `CHECK (parent_id <> id)`).
- uq `(syllabus_version_id, stable_key)`; GiST on `path`; ix `(parent_id, sort)`; ix `(syllabus_version_id, level_code)`.
- `track_levels` PK `(track_id, depth)`; a node's `level_code` must exist in its track's levels (service validation plus a deferred check in import).

**Enrolments**
- `track_enrolments.track_id` → `curriculum.tracks`; `syllabus_version_id` → `curriculum.syllabus_versions` (cross-schema FKs allowed, 01 §1.1).
- uq partial `(user_id, track_id, exam_year) WHERE status='active'`.

**Question bank**
- `question_versions.question_id` → `questions` `ON DELETE RESTRICT`; uq `(question_id, version_no)`; `supersedes_id` → `question_versions`.
- `questions.current_version_id` → `question_versions` (`DEFERRABLE INITIALLY DEFERRED` so both rows can be created in one transaction).
- `qv_content` PK `(question_version_id, lang)`, `CHECK (lang IN ('bn','en'))`.
- `cq_subparts` uq `(question_version_id, ordinal)`; `rubric_points.subpart_id` → `cq_subparts` `ON DELETE CASCADE` (only while the version is a draft; published versions cannot be deleted).
- `question_node_map` PK `(question_id, node_id)`; ix `(node_id, question_id)`; node FK → `curriculum.taxonomy_nodes`.
- `papers`: ix `(board_code, year, unit)`. `paper_items` PK `(paper_id, position)`; `question_version_id` FK.
- `concept_notes.node_id` → taxonomy nodes.
- Indexes on `questions`: `(status)`, `(tenant_id) WHERE tenant_id IS NOT NULL`. On `question_versions`: `(status)`, `(source_board, source_year)`, GIN on `tags`.

**Immutability (defence in depth)**
- A trigger `qbank.forbid_published_update` on `question_versions`, `qv_content`, `cq_subparts` and `rubric_points` rejects `UPDATE` or `DELETE` when the version's `status IN ('published','retired')`.
- Allowed column exceptions: `status` (to `retired`), `retired_at`, `render_status`, `index_status`, `difficulty_computed`, and `qv_content.rendered_*`.
- This is the one place a trigger is justified: QB-06 promises edits never break past attempts.

**Rights (C22)**
- `CHECK (status <> 'published' OR source_rights <> 'unknown')` on `questions`.

**CMS**
- `key_verifications` `CHECK (verifier_id <> author_id)`; uq `(question_version_id, verifier_id)`.
- `review_assignments` ix `(assignee_id, status, due_at)`, ix `(subject_node_id, status, kind)`.
- `error_reports` ix `(status, triage_due_at)`, ix `(question_id, status)`.

**Search**
- `search_documents` uq `(entity_type, entity_id, lang)`.
- GIN on `tsv` (`simple` config), `node_ids` and `math_tokens`; GIN `gin_trgm_ops` on `folded_text` and `banglish_text`.
- Ix `(status, tenant_id)`.

### B.3 Migration sequence

| Revision | Content |
|---|---|
| `b02_01_curriculum_core` | `boards`, `tracks`, `track_levels`, `syllabus_versions` |
| `b02_02_curriculum_nodes` | `taxonomy_nodes` (ltree, GiST), `track_exam_dates` |
| `b02_03_identity_enrolments` | `track_enrolments`; `profiles.board_code` FK (expand) |
| `b02_04_qbank_questions` | `questions`, `question_versions` (deferred FK), `qv_content` |
| `b02_05_qbank_written` | `cq_subparts`, `rubric_points` |
| `b02_06_qbank_mapping_media` | `question_node_map`, `question_media`, `concept_notes` |
| `b02_07_qbank_papers` | `papers`, `paper_items`, `paper_tracks` |
| `b02_08_qbank_imports` | `import_jobs`, `import_rows`, `rendering_failures` |
| `b02_09_qbank_immutability` | Trigger function and triggers; rights check constraint |
| `b02_10_cms_workflow` | `workflow_events`, `key_verifications`, `review_assignments`, `editor_drafts` |
| `b02_11_cms_error_reports` | `error_reports` |
| `b02_12_platform_search` | `search_documents` with GIN and trigram indexes |
| `b02_13_permissions_seed` | Permission codes for content and curriculum; default role → permission mapping for `content_author` and `reviewer` |

Seed data: `scripts/seed_curriculum.py` loads tracks, levels and trees from `seed/curriculum/*.yaml`. These cover the pilot tracks in full and skeletons of the others. `boards` is seeded in `b02_01`, since it is tiny reference data.

### B.4 Transaction requirements

| Operation | Boundary |
|---|---|
| Create question with first version | `questions` + `question_versions` (v1, draft) + `qv_content` (1–2 langs) + subparts/rubrics + `question_node_map` + `workflow_events` in one transaction (deferred FK) |
| Save draft | Upsert `editor_drafts` only (no version write) |
| New version from draft | Lock the question row; `version_no = max + 1`; copy-forward unchanged children; `supersedes_id` = current published version (or null); status `draft` |
| Submit for review | Version `draft → in_review`; create `review_assignments(kind=verify)` for an eligible reviewer (scope covers the subject, not the author); `workflow_events` |
| Blind verification | Lock the version row (`FOR UPDATE`); insert `key_verifications`; compare with the stored key using the type's comparator. Match → `verified`. Mismatch → create a `tiebreak` assignment to a third person. Then the tie-break result: equal to author → `verified`; equal to the first verifier → back to `draft` with a note; neither → `draft`. Single transaction per verification (01 §5.2 R7). |
| Publish | Lock the question row. Check that `source_rights <> unknown`, the version is `verified`, and `supersedes_id` equals the current published version (R8). Set the version to `published`, the previous published version to `retired`, `questions.current_version_id`, `workflow_events`, outbox `question.published` (or `question.corrected` when `supersedes_id` is set and the key differs). Enqueue the `qb.render` and `search.index` jobs (via the outbox consumer). |
| Import commit | Per batch of 200 valid rows: create questions as drafts. The job is resumable from `import_rows.status`. |
| Error-report triage | Lock the report; merge into an open report on the same question (sets `merged_into_id`); audited |

### B.5 Data-integrity requirements

- A published version and its content, subparts and rubrics never change (trigger plus service checks plus tests).
- `answer_key` jsonb must validate against the type's pydantic model on every write (service) and on import.
- `qv_content.content_sha256` is recomputed on each write; rendering is keyed on it so re-renders are skipped when unchanged.
- A question becomes **selectable** (returned by `qb.get_selectable_versions`) only when `status = published`, `render_status = done` and `index_status = done` (v2 §7.1 step 6).
- Every `question_node_map` node must belong to a syllabus version of a track the question's paper or tags say it serves. Service-level validation produces warnings only; cross-track mapping is legitimate under TAX-03.

---

## C. Backend implementation

### C.1 Implementation steps (exact order)

1. TAX models, repositories and migrations `b02_01`–`b02_02`. Tree service: create, move (path rewrite of the subtree in one statement: `UPDATE … SET path = :new || subpath(path, nlevel(:old))`), reorder, copy-forward a syllabus version (clone the nodes with new ids, the same `stable_key`, and a parent map). Public read API with caching. Seed loader.
2. AUTH-05 enrolments: migration `b02_03`, service and routes. The public `auth.get_active_enrolments(user_id)` is used by later builds.
3. QB answer-key type system: `qb/contracts/question_types.py` (a pydantic discriminated union per type), validators and comparators (`keys_equal(type, a, b)` for blind verification, `score(type, key, response)` for B3).
4. QB models and migrations `b02_04`–`b02_09`. Repositories. Services:
   - create question;
   - new version;
   - draft autosave (via CMS);
   - get versions (public, with and without keys);
   - media confirm;
   - papers;
   - concept notes.
5. Rendering: `tools/katex-render` Node CLI; the `qb.render` job (render body, options and explanation per language; sanitise HTML with an allow-list; store `rendered_*`; record failures in `rendering_failures`); the preview service (synchronous call to the same CLI with a 3 s timeout).
6. CMS workflow (migration `b02_10`):
   - the state machine module (`transitions.py`: allowed `(from, to, permission)` table);
   - submit for review;
   - assignment selection (least-loaded eligible reviewer in scope, excluding the author);
   - blind verification and tie-break;
   - publish and retire through the QB public API (CMS owns the workflow; QB owns the rows; CMS calls `qb.set_status(...)` inside its transaction by passing the session);
   - assignment queue routes.
7. Search indexing: the `search.index` job building the `search_documents` row per (version, lang) — `tsv`, `folded_text`, `banglish_text`, `math_tokens`, `node_ids` including ancestors, `syllabus_version_ids`. Search query service (filters plus lexical rank plus trigram similarity). Admin search route with all metadata filters. Bulk edit, tag and move (each creates new draft versions or updates mapping and tags, which are version metadata; tags and node mapping on published content change through a new version, while `question_node_map` is question-level and editable with an audit row).
8. Imports (migration `b02_08`): upload presign purpose `import_file`; parsers for xlsx (openpyxl), csv, docx (python-docx, template styles) and json; row validation using the same pydantic type models; the report as an `import_rows` listing plus an xlsx report file in S3; the commit job.
9. Error reports (migration `b02_11`): the admin queue, triage, merge, SLA timers (`triage_due_at = created + 24 h`, `resolve_due_at = created + 72 h`), and an SLA breach job (`cms.error_reports.sla_check`, hourly) that publishes `cms.sla_breached` for alerting. The student creation route comes in B3, but the service function `cms.create_error_report(...)` is built and tested now.
10. Media: presign purpose `question_media` (images ≤ 1 MB, SVG sanitised server-side with an allow-list, audio ≤ 5 MB), and confirmation into `question_media`. `qb.media_url(storage_key)` returns a 10-minute signed GET (CDN in front from B6).
11. Permissions seed (`b02_13`), the authorization matrix tests, the OpenAPI snapshot, and seed scripts for the dev bank: 200 sample questions covering every type.

### C.2 Folder structure changes

New: `modules/tax/internal/...`, `modules/qb/internal/...` (plus `internal/render/`, `internal/importers/`), `modules/cms/internal/...`, `modules/nfr/internal/search/`, `backend/tools/katex-render/` (Node, own `package.json` and lockfile; `index.js` ≤ 120 lines), `backend/seed/curriculum/`, and `tests/modules/{tax,qb,cms}/`.

### C.3 Files to create

**TAX (`modules/tax/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `tax/__init__.py` | Public: `get_tree`, `get_node`, `get_ancestors(node_ids)`, `is_descendant`, `get_syllabus_version`, `get_track`, `get_exam_date`, `routers()` | 50 |
| `tax/contracts/dto.py` | `TrackDTO`, `SyllabusVersionDTO`, `NodeDTO` (with `path`, `ancestors`) | 70 |
| `tax/internal/models/curriculum.py` | `Board`, `Track`, `TrackLevel`, `SyllabusVersion`, `TrackExamDate` | 110 |
| `tax/internal/models/node.py` | `TaxonomyNode` with an `ltree` column type (`sqlalchemy_utils`-free custom type) | 70 |
| `tax/internal/models/ltree_type.py` | Minimal `LtreeType` TypeDecorator plus label encoding (uuid hex without dashes) | 50 |
| `tax/internal/repositories/tracks.py` | Tracks, versions, levels, exam dates | 100 |
| `tax/internal/repositories/nodes.py` | Get subtree by path (`path <@ :p`), ancestors (`path @> :p`), children ordered, bulk insert, subtree move | 140 |
| `tax/internal/services/tree.py` | Create, move, reorder, deactivate nodes with validation (level order, same version) | 150 |
| `tax/internal/services/copy_forward.py` | Clone a syllabus version: nodes, keeping `stable_key` | 110 |
| `tax/internal/services/read_cache.py` | Tree read with a Redis cache keyed by `(syllabus_version_id, updated_at)`; edge cache headers | 80 |
| `tax/internal/services/tree_import.py` | Bulk tree import from CSV/JSON (`stable_key`, parent key, names, level, sort, is_free) | 130 |
| `tax/internal/routes/public.py` | `/v1/tracks…`, `/v1/syllabus-versions/{id}/tree`, `/v1/nodes/{id}`, exam dates | 100 |
| `tax/internal/routes/admin.py` | Admin tracks, versions, nodes, import, exam dates | 150 |
| `tax/internal/schemas/*.py` (`public.py`, `admin.py`) | Schemas | 2 × 100 |
| `scripts/seed_curriculum.py` | YAML → tree import service | 80 |

**AUTH additions**

| Path | Responsibility | ~Lines |
|---|---|---|
| `auth/internal/models/enrolment.py` | `TrackEnrolment` | 50 |
| `auth/internal/repositories/enrolments.py` | List, create, update, active for user | 70 |
| `auth/internal/services/enrolments.py` | Enrol (validate track active, syllabus version for year via TAX, group required for tracks whose levels include group), change group or version, close | 120 |
| `auth/internal/routes/enrolments.py` | `/v1/me/enrolments` routes | 80 |
| `auth/internal/schemas/enrolments.py` | Schemas | 60 |

**QB (`modules/qb/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `qb/__init__.py` | Public: `get_versions(ids, include_key=False, lang)`, `get_selectable_versions(filters)`, `get_rubric(version_id)`, `score_response(version, response)`, `keys_equal`, `set_status(session, …)`, `create_question(session, …)`, `media_url`, `routers()`, `job_handlers()` | 70 |
| `qb/contracts/question_types.py` | Discriminated unions `AnswerKey` and `Response` for 10 types (MCQ single, multi-statement, stimulus, CQ, short, essay, fill-in, true/false, matching, numeric with `tolerance_abs`/`tolerance_rel`) | 170 |
| `qb/contracts/versions.py` | `QuestionVersionDTO` (with or without key), `ContentDTO`, `SubpartDTO`, `RubricPointDTO` | 110 |
| `qb/internal/models/question.py` | `Question`, `QuestionVersion` | 120 |
| `qb/internal/models/content.py` | `QvContent`, `QuestionMedia` | 70 |
| `qb/internal/models/written.py` | `CqSubpart`, `RubricPoint` | 60 |
| `qb/internal/models/papers.py` | `Paper`, `PaperItem`, `PaperTrack`, `ConceptNote` | 100 |
| `qb/internal/models/imports.py` | `ImportJob`, `ImportRow`, `RenderingFailure` | 80 |
| `qb/internal/models/mapping.py` | `QuestionNodeMap` | 30 |
| `qb/internal/repositories/questions.py` | Create, lock, versions by ids (selectinload content/subparts/rubrics), next version no | 150 |
| `qb/internal/repositories/versions_read.py` | Bulk read for public use, with selectable filter | 110 |
| `qb/internal/repositories/papers.py` | Papers CRUD and items | 90 |
| `qb/internal/repositories/notes.py` | Concept notes | 50 |
| `qb/internal/repositories/imports.py` | Jobs and rows | 80 |
| `qb/internal/services/scoring.py` | `score_response(type, key, response, marks, negative)` per type; numeric tolerance; matching partial credit (off at P0); CQ and essay → `None` (self, teacher or AI scored) | 150 |
| `qb/internal/services/key_compare.py` | `keys_equal(type, a, b)`: order-insensitive for multi-select, normalised for fill-in (NFC, case, whitespace, Bangla digits) | 80 |
| `qb/internal/services/authoring.py` | Create a question with v1; new version from a draft payload; copy-forward children | 160 |
| `qb/internal/services/validation.py` | Cross-field checks: options present for MCQ types; CQ subparts sum to marks; rubric points sum to the subpart's marks; languages present per policy (≥ 1, both for bilingual tracks) | 130 |
| `qb/internal/services/status.py` | `set_status(session, version_id, to, actor)` used by CMS; publish and retire side effects; outbox events | 120 |
| `qb/internal/services/read.py` | `get_versions` with a Redis cache keyed `qv:{id}:{lang}:{key?}` (immutable when published) | 100 |
| `qb/internal/services/media.py` | Media confirm, SVG sanitisation (`defusedxml` plus an element allow-list), signed URL | 120 |
| `qb/internal/services/papers.py` | Paper create and edit (versions must be published), tracks | 100 |
| `qb/internal/render/katex_cli.py` | Subprocess wrapper: JSON batch in, HTML out; timeout; error capture | 90 |
| `qb/internal/render/html_sanitize.py` | Allow-list sanitiser for rendered HTML (KaTeX classes, tables, img with signed src placeholder) | 90 |
| `qb/internal/render/render_job.py` | `qb.render` job: per version and language, render fields, store, mark `render_status`, failures | 120 |
| `qb/internal/importers/base.py` | `ImportRowModel`, mapping profile, row → create-question payload | 120 |
| `qb/internal/importers/xlsx.py`, `csv_.py`, `docx.py`, `json_.py` | Format parsers | 4 × 100 |
| `qb/internal/importers/job.py` | `qb.import.validate` and `qb.import.commit` jobs; report xlsx | 150 |
| `qb/internal/routes/admin_questions.py` | Create, get, versions, preview, bulk | 160 |
| `qb/internal/routes/admin_papers.py` | Papers and concept notes | 110 |
| `qb/internal/routes/admin_imports.py` | Imports | 80 |
| `qb/internal/schemas/*.py` (`questions.py`, `papers.py`, `imports.py`) | Schemas | 3 × 120 |
| `tools/katex-render/index.js` | Reads JSON lines `{id, tex, display}` → `katex.renderToString` with `throwOnError: false`, `strict: "warn"`, `trust: false`; Bangla digits pass through | 80 |

**CMS (`modules/cms/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `cms/__init__.py` | Public: `create_error_report(session, …)`, `routers()`, `job_handlers()` | 30 |
| `cms/internal/models/workflow.py` | `WorkflowEvent`, `KeyVerification`, `ReviewAssignment`, `EditorDraft` | 110 |
| `cms/internal/models/error_report.py` | `ErrorReport` | 50 |
| `cms/internal/repositories/assignments.py` | Queue queries (by assignee, scope), load counts per reviewer, create and complete | 120 |
| `cms/internal/repositories/verifications.py` | Insert, by version | 50 |
| `cms/internal/repositories/error_reports.py` | Queue, lock, merge | 90 |
| `cms/internal/repositories/drafts.py` | Upsert and get | 40 |
| `cms/internal/services/transitions.py` | Table of allowed transitions and required permission; `assert_transition` | 70 |
| `cms/internal/services/submit.py` | Submit for review; create a verify assignment | 90 |
| `cms/internal/services/assign.py` | Eligible reviewer selection (`auth.list_users_with_permission(scope)`, exclude the author, least open assignments, round-robin tiebreak) | 100 |
| `cms/internal/services/verify.py` | Blind verification and tie-break logic (§B.4) | 150 |
| `cms/internal/services/publish.py` | Publish and retire with checks; calls `qb.set_status` | 90 |
| `cms/internal/services/error_reports.py` | Create (moderated text), triage, merge, SLA timers | 140 |
| `cms/internal/services/drafts.py` | Autosave with optimistic version (`updated_at` match → else 409 `version_conflict`) | 60 |
| `cms/internal/services/bulk.py` | Bulk tag, move, edit with a per-item result list (max 500 per request) | 130 |
| `cms/internal/jobs/sla.py` | Hourly SLA check | 60 |
| `cms/internal/routes/admin_workflow.py` | Draft, submit, verifications, publish, retire, preview hook | 150 |
| `cms/internal/routes/admin_queues.py` | Assignments, error reports | 120 |
| `cms/internal/schemas/*.py` (`workflow.py`, `queues.py`) | Schemas | 2 × 110 |

The verification response never echoes the author's key. The verifier's view (`GET /v1/admin/questions/{id}` with `role=verifier`) omits `answer_key` until the verifier has submitted (the service enforces this; tested).

**Search (`modules/nfr/internal/search/`)**

| Path | Responsibility | ~Lines |
|---|---|---|
| `nfr/internal/search/models.py` | `SearchDocument` | 60 |
| `nfr/internal/search/text_fields.py` | Build `tsv` input (normalised Bangla and English tokens), `folded_text`, `banglish_text` from `shared.bangla_text` | 120 |
| `nfr/internal/search/math_canonical.py` | LaTeX → canonical tokens: strip styling (`\mathrm`, `\left`/`\right`, spaces), unify commands (`\dfrac`→`\frac`), sort commutative `+` and `*` operands, emit sub-expression tokens; `x^2+2x+1` ≡ `1+2x+x^{2}` | 170 |
| `nfr/internal/search/index_job.py` | `search.index` consumer for `question.published`/`question.retired`; upsert or deactivate rows; set `index_status` via `qb.set_index_status` | 110 |
| `nfr/internal/search/query.py` | `search_questions(filters, q, lang, tenant, limit, cursor)`: metadata and permission filters, then lexical `ts_rank` ∪ trigram on folded and banglish ∪ math token overlap, merged by reciprocal rank fusion (vector added in B4) | 170 |
| `nfr/internal/search/__init__.py` | Re-exported via `nfr.search_questions` | 20 |

Using `query.py` from CMS admin search is allowed through the NFR public API.

### C.4 Business logic and validation rules

| Area | Rule |
|---|---|
| Node levels | A node's depth equals its parent's depth + 1, and `level_code` equals `track_levels[depth]`. Moves keep levels consistent; a subtree moves only to a parent at the same depth. |
| Copy-forward | Allowed only into an empty `draft` syllabus version of the same track. `stable_key`s are kept. `question_node_map` is not copied automatically; the content team maps questions to new-year nodes with a bulk tool, which suggests the mapping by `stable_key` (preview, then apply). |
| Answer key per type | MCQ: one correct label among options (2–6). Multi-statement: one correct combination label (i/ii/iii pattern). Stimulus: shared stimulus in `body`, single correct. True/false: boolean. Fill-in: 1–5 accepted strings per blank. Matching: a complete bijection map. Numeric: value plus tolerance (absolute or relative, one required). CQ: subparts (3 or 4 typical; 1–6 allowed) with marks; no auto key. Short and essay: model answer and rubric, no auto key. |
| Marks | `marks > 0`. For CQ, `sum(subparts.marks) = marks`. For a rubric, `sum(points.marks) = subpart.marks` (warning in draft; error on submit). |
| Languages | At least one of bn and en. A track flag `bilingual_required` (in `tracks` metadata) forces both before submit. |
| Rights | `source_rights` is required at creation and at import. `unknown` cannot be submitted for publish (blocked at submit with 422 `rights_unknown`, and by the DB check at publish). |
| Workflow | `draft → in_review` (author, `content.author`); `in_review → verified` (verification); `in_review → draft` (reviewer reject, with a note); `verified → published` (`content.publish`); `published → retired` (`content.publish`); a new version starts in `draft`. An author cannot verify or publish their own version (verify is enforced by the DB; publish by the service check against `authored_by`). |
| Assignment scope | A reviewer is eligible if their `content.verify` grant scope covers the question's primary node (subject or track ancestor, via `tax.is_descendant`). |
| Error-report merge | A new report on a question with an open report of the same kind merges (`merged_into_id`) and increments a count in `details`; the reporter list stays private. |
| Bulk ops | ≤ 500 items; each item validated independently; the response lists per-item success or error; the whole request is audited with a summary. |
| Import | Max 20,000 rows or 50 MB per file. Rows with errors are reported, never partially imported. The duplicate check is B4. |
| Media | Images: jpeg, png or webp, ≤ 1 MB, ≤ 2,000 px edge. SVG ≤ 200 KB, sanitised. Audio: mp3 or ogg ≤ 5 MB. `alt_text_bn` is required for images on publish (NFR-11 groundwork). |

### C.5 Jobs and workers

| Job kind | Trigger | Notes |
|---|---|---|
| `qb.render` | Consumer of `question.version_ready_for_render` (emitted at submit and publish) | Batched per version; idempotent on `content_sha256` |
| `search.index` | Consumer of `question.published`, `question.retired` | Sets `index_status` |
| `qb.import.validate` | Enqueued on import create | Writes `import_rows` |
| `qb.import.commit` | Enqueued on commit | Batches of 200; resumable |
| `cms.error_reports.sla_check` | Hourly | Emits `cms.sla_breached` |
| `cms.assignments.rebalance` | Every 15 min | Reassigns stale assignments (> 72 h untouched) |

Worker queues come from the canonical list in `core/jobs/queues.py` (R-04):
- `imports` for `qb.render`, `search.index`, `qb.import.validate` and `qb.import.commit`;
- `maintenance` for `cms.error_reports.sla_check` and `cms.assignments.rebalance` (hourly and 15-minute schedules with `dedupe_key` plus `dedupe_until` per window).

The worker image includes Node (`WITH_NODE=1`).

### C.6 Caching

- `qv:{question_version_id}:{lang}:{k|nk}`: published version DTOs, TTL 7 days (immutable once published); populated on read. **Proposed addition** to 01 §3.17.
- `tax:tree:{syllabus_version_id}:{updated_epoch}`: TTL 1 day. **Proposed addition.**
- HTTP: `/v1/tracks`, trees and nodes send `Cache-Control: public, max-age=300` and an `ETag` (edge-cached).

### C.7 Events (outbox)

`question.published {question_id, question_version_id, supersedes_id, node_ids, tenant_id}`, `question.corrected {question_id, old_version_id, new_version_id, key_changed: bool}`, `question.retired`, `question.version_ready_for_render`, `cms.sla_breached`, `enrolment.created`. Payload models live in `qb/contracts/events.py`, `cms/contracts/events.py` and `auth/contracts/events.py`; each is ~40 lines.

### C.8 Security requirements

- All admin routes need `aud=admin` and the scoped permissions in 14 §3.5. Every write is audited.
- Verifiers never receive the author's key before submitting (an authorization test).
- Rendered HTML is sanitised (no script, no event handlers, no external URLs except signed media placeholders); KaTeX `trust: false`.
- SVG is sanitised; imports are parsed with defused XML and no macros (docx: python-docx does not execute macros; reject `.docm`).
- Signed media URLs expire in 10 minutes; object keys are unguessable (`media/{uuid7}/{sha256[:16]}`).

### C.9 Configuration

| Variables |
|---|
| `KATEX_CLI_PATH`, `KATEX_TIMEOUT_MS` (3,000), `IMPORT_MAX_ROWS` (20,000), `IMPORT_MAX_BYTES`, `MEDIA_SIGNED_URL_TTL_S` (600), `S3_BUCKET_CONTENT`, `CMS_TRIAGE_SLA_H` (24), `CMS_RESOLVE_SLA_H` (72) |

`docker-compose.yml` adds a `worker-node` service built with `WITH_NODE=1` for local renders.

---

## D. API contracts

All admin endpoints need `aud=admin`, tier **T-admin** and the permission shown. Writes marked **R** require `Idempotency-Key`.

### D.1 Curriculum and enrolments

**`GET /v1/tracks`** (Public, T-read)
- Query: `?kind=academic|admission|job|madrasah|technical`
- Response: `{items: [TrackDTO{id, code, kind, name_bn, name_en, icon, sort}]}`. ETag.

**`GET /v1/tracks/{track_id}/syllabus-versions`** → `{items: [{id, year, status}]}`. 404 for an unknown track.

**`GET /v1/syllabus-versions/{id}/tree`**
- Query: `?root=node_id&depth=1..8` (default full when the tree has ≤ 5,000 nodes, otherwise depth 3)
- Response: `{version: {...}, nodes: [NodeDTO{id, parent_id, level_code, depth, stable_key, name_bn, name_en, sort, icon, is_free}]}`
- Only `active` versions are visible to the public; draft versions are visible to staff.

**`GET /v1/nodes/{node_id}`** → `NodeDTO` plus `{ancestors: [NodeDTO], children: [NodeDTO]}`

**`GET /v1/tracks/{track_id}/exam-dates`** → `{items: [{exam_year, starts_on, is_confirmed, source_url}]}`

**`POST /v1/admin/tracks`** (Staff:curriculum, R)
- `{code: slug (3–40), kind, name_bn, name_en, icon?, sort, levels: [{depth, level_code, name_bn, name_en}] (1–8)}` → 201 `TrackDTO`
- Errors: 409 duplicate code; 422.

**`PATCH /v1/admin/tracks/{id}`** → names, icon, sort, `is_active`. Levels change only while no syllabus version is active (409 otherwise).

**`POST /v1/admin/syllabus-versions`** (R)
- `{track_id, year (2000–2100), copy_from_version_id?}` → 201
- Errors: 409 for an existing (track, year); 422 when `copy_from` is from another track.

**`PATCH /v1/admin/syllabus-versions/{id}`** → `{status: active|retired}`. Activation requires ≥ 1 node; audited.

**`POST /v1/admin/nodes`** (R)
- `{syllabus_version_id, parent_id?, level_code, stable_key, name_bn, name_en, sort, icon?, is_free, marks_weight?}` → 201
- Errors: 422 level mismatch; 409 duplicate `stable_key`.

**`PATCH /v1/admin/nodes/{id}`**
- `{name_bn?, name_en?, sort?, icon?, is_free?, is_active?, parent_id? (move)}` → 200
- Errors: 422 invalid move; 409 `version_conflict` (stale `If-Match` ETag).

**`POST /v1/admin/nodes:import`** (R)
- `{syllabus_version_id, upload_key}`, a CSV or JSON file presigned with purpose `tree_import`
- Response 202: `{job_id}`, reported through `GET /v1/admin/imports/{id}`. The same import table is reused, with `kind = tree`. **Proposed addition**: allow `kind = tree` in `import_jobs`.

**`PUT /v1/admin/tracks/{id}/exam-dates/{year}`** → `{starts_on, is_confirmed, source_url?}` → 200. Audited.

**`GET /v1/me/enrolments`** (User, T-read) → `{items: [{id, track, syllabus_version, exam_year, group_code, version_lang, status, enrolled_at}]}`

**`POST /v1/me/enrolments`** (User, T-write, O)
- `{track_id, exam_year, group_code?, version_lang}` → 201
- Errors: 409 `already_enrolled`; 422 (no active syllabus version for the year; group required); 404 track.
- Emits `enrolment.created`.

**`PATCH /v1/me/enrolments/{id}`** (Owner) → `{group_code?, version_lang?, status?: closed}`. A group change keeps history (same enrolment; attempts keep their own context). Errors: 404, 422.

### D.2 Question bank and CMS

**`POST /v1/admin/questions`** (Role:content.author, R)

Request:
```json
{
  "type": "mcq_single|mcq_multi_statement|mcq_stimulus|cq|short|essay|fill_in|true_false|matching|numeric",
  "source_rights": "own|licensed|public_board|unknown", "rights_note": "≤500",
  "node_ids": ["uuid", "…"], "primary_node_id": "uuid",
  "version": {
    "answer_key": {"…typed per type…"}, "marks": 1.0, "time_estimate_s": 60,
    "difficulty_author": 1, "bloom_level": "knowledge|comprehension|application|higher",
    "source": {"board": "dhaka", "year": 2023, "school": null, "unit": null, "bcs_no": null, "exam_name": null},
    "tags": ["…"], "video_url": "https://…", "concept_note_id": null,
    "content": {"bn": {"body": "…", "options": [{"label": "ka", "text": "…"}], "explanation": "…"}, "en": {"…": "…"}},
    "subparts": [{"label": "ক", "ordinal": 1, "marks": 1, "bloom_level": "knowledge", "model_answer_bn": "…",
                  "rubric": [{"ordinal": 1, "description_bn": "…", "marks": 1}]}]
  }
}
```

- Response 201: `{question_id, question_version_id, status: "draft"}`
- Validation: §C.4. Errors: 422 `validation_error` (field paths); 404 node.

**`GET /v1/admin/questions/{id}`** (Role:content.read)
- Response: `{question, versions: [summary], current: QuestionVersionDTO (full, with key, except for a verifier with an open verify assignment), workflow: [events], draft?: {payload, updated_at}}`

**`PUT /v1/admin/questions/{id}/draft`** (Role:content.author)
- `{payload: {...same shape as version...}, base_updated_at?}` → 200 `{updated_at}`
- Errors: 409 `version_conflict`.

**`POST /v1/admin/questions/{id}/versions`** (R) → creates a version from the draft (or a body) → 201 `{question_version_id, version_no}`. Errors: 422; 409 if a draft version already exists.

**`POST /v1/admin/questions/{id}:preview`**
- `{payload | question_version_id, lang, device: mobile|desktop}` → 200 `{html: {body, options, explanation}, warnings: [{field, message}]}`
- Timeout 3 s → 503 `unavailable`.

**`POST /v1/admin/questions/{id}:submit-review`** (R)
- `{question_version_id, note?}` → 200 `{status: in_review, assignment_id}`
- Errors: 422 `rights_unknown`, validation; 409 wrong state.

**`POST /v1/admin/question-versions/{id}/verifications`** (Role:content.verify, R)
- `{entered_key: AnswerKey, note?}` → 200 `{result: verified|tiebreak_required|returned_to_draft, matches: bool}`
- Errors: 403 (the author, or no open assignment for this verifier); 409 (already verified by you, or wrong state). CQ, short and essay: the verifier confirms the rubric and model answer instead (`entered_key = {"confirm": true}`), and 2 confirmations are required.

**`POST /v1/admin/question-versions/{id}:publish`** (Role:content.publish, R) → 200 `{status: published, selectable: false}` (it becomes selectable after render and index). Errors: 409 state or supersede mismatch; 422 rights; 403 own version.

**`POST /v1/admin/question-versions/{id}:retire`** (R) → `{reason}` → 200. Audited.

**`GET /v1/admin/questions`** (Role:content.read)
- Query: `?q=&lang=&type=&status=&node_id=&include_descendants=true&source_board=&source_year=&bloom=&difficulty_min=&difficulty_max=&tags=&rights=&author_id=&has_explanation=&tenant_id=&cursor=&limit=`
- Response: `Page<{question_id, version_id, type, status, snippet_bn, snippet_en, nodes, source, difficulty, updated_at, score?}>`
- `q` uses lexical, trigram, Banglish and maths search.

**`POST /v1/admin/questions:bulk`** (Role:content.author, R)
- `{question_ids: [≤500], action: add_tags|remove_tags|map_nodes|unmap_nodes|set_difficulty|retire, params: {...}}` → 200 `{results: [{question_id, ok, error?}]}`

**`GET /v1/admin/assignments`** → `?kind=&status=open&cursor=` → `Page<{id, kind, question_id, version_id, subject, due_at, assigned_at}>`

**`POST /v1/admin/assignments`** (Role:content.lead, R) → `{question_ids, assignee_id, kind}` → 201 `{created}`. Errors: 422 when the assignee is out of scope or is the author.

**`POST /v1/admin/papers`** (R)
- `{kind, board_code?, year, unit?, exam_name?, title_bn, title_en, total_marks, duration_min, track_ids: [], items: [{position, question_version_id, section_label?}]}` → 201
- Errors: 422 (versions not published; duplicate positions).

**`PATCH /v1/admin/papers/{id}`** → metadata; items only while the paper is `draft`. Status `published` once complete.

**`POST /v1/admin/concept-notes`** / **`PATCH …/{id}`** → `{node_id, kind: concept, title_bn, title_en?, body}` → 201 (rendered by the same job).

**`POST /v1/admin/imports`** (R)
- `{kind: xlsx|csv|docx|json|tree, upload_key, source_rights, rights_note?, mapping_profile?: {...}, default_node_id?}` → 202 `{import_id, status: validating}`

**`GET /v1/admin/imports/{id}`** → `{status, totals: {rows, valid, invalid}, report_url (signed), rows: Page<{row_no, status, errors}>}`

**`POST /v1/admin/imports/{id}:commit`** (R) → 202 `{status: committing}`. Errors: 409 when not validated or already committed.

**`GET /v1/admin/error-reports`** (Role:content.triage) → `?status=&kind=&subject_node_id=&overdue=true&cursor=` → `Page<{id, question_id, kind, text, count, status, triage_due_at, resolve_due_at, age_h}>`

**`POST /v1/admin/error-reports/{id}:triage`** (R) → `{action: accept|reject|merge, merge_into_id?, note}` → 200. Errors: 409 state.

**`GET /v1/uploads/{purpose}/presign`**: new purposes `import_file`, `tree_import`, `question_media` (staff only).

---

## E. Testing strategy

| File | Type | Cases |
|---|---|---|
| `tests/modules/tax/test_tree_service.py` | db | Create nodes at correct depths; level mismatch 422; move a subtree rewrites paths of all descendants; reorder; deactivate hides from the public tree |
| `tests/modules/tax/test_copy_forward.py` | db | Clone keeps `stable_key`s and structure, gives new ids; target must be an empty draft |
| `tests/modules/tax/test_tree_import.py` | integration | CSV with parents out of order; unknown parent key → row error; idempotent re-import |
| `tests/modules/tax/test_public_routes.py` | api | ETag and 304; draft versions hidden from the public; depth parameter |
| `tests/modules/auth/test_enrolments.py` | api | Multi-track enrolment; duplicate active → 409; no syllabus for the year → 422; close and re-enrol |
| `tests/modules/qb/test_question_types.py` | unit (table-driven) | Valid and invalid keys for all 10 types; numeric tolerance edges (abs vs rel, negative values, exact boundary); matching bijection |
| `tests/modules/qb/test_scoring.py` | unit | `score_response` for each auto-scored type, including negative marking values 0.25 and 0.5, unanswered = skipped, wrong option set for multi-statement |
| `tests/modules/qb/test_key_compare.py` | unit | Order-insensitive multi-select; fill-in normalisation (Bangla digits, NFC, zero-width) |
| `tests/modules/qb/test_authoring.py` | db | Create with both languages, CQ with 3 and 4 parts, rubric sum checks, new version copies children, version numbers increase |
| `tests/modules/qb/test_immutability.py` | db | UPDATE of a published version's body raises (trigger); allowed columns update; retired is immutable too; service returns 409 before hitting the trigger |
| `tests/modules/qb/test_render_job.py` | integration | Node CLI renders `\frac{1}{2}` and Bangla text; invalid TeX records `rendering_failures` without crashing; unchanged hash skipped; sanitiser strips `<script>` and `onerror` |
| `tests/modules/qb/test_media.py` | api | Presign limits; SVG with `<script>` sanitised; image dimension check; signed URL expires |
| `tests/modules/qb/test_importers.py` | integration | Fixture files per format (xlsx, csv, docx template, json): valid rows → drafts; invalid rows reported with row numbers and field errors; 20,001 rows rejected; docm rejected |
| `tests/modules/cms/test_transitions.py` | unit | Every allowed and forbidden transition × permission |
| `tests/modules/cms/test_blind_verification.py` | db | Match → verified; mismatch → tiebreak assignment; tiebreak equal to author → verified, equal to verifier → draft, neither → draft; CQ needs 2 confirmations; the author as verifier → DB check violation and 403 at the service |
| `tests/concurrency/test_verify_race.py` | concurrency | Two verifiers submit concurrently on the same version → exactly one transition; both rows recorded; final status deterministic |
| `tests/modules/cms/test_verifier_cannot_see_key.py` | authorization | A verifier with an open assignment gets the version without `answer_key`; after submitting, the key is visible |
| `tests/modules/cms/test_publish.py` | db | Unknown rights → 422 and DB check; supersede mismatch → 409; publishing v2 retires v1; outbox `question.published` or `question.corrected` with `key_changed`; not selectable until render and index done |
| `tests/concurrency/test_publish_race.py` | concurrency | Two publishes of different versions of one question → one wins, the other 409 (R8) |
| `tests/modules/cms/test_assignment.py` | db | Eligible reviewer in scope excluding the author; least-loaded; no eligible reviewer → assignment unassigned and an alert event |
| `tests/modules/cms/test_error_reports.py` | db | Create (moderated text), merge into an open report, SLA timestamps, overdue filter, SLA job emits an event once |
| `tests/modules/nfr/search/test_math_canonical.py` | unit | `x^2+2x+1` ≡ `1+2x+x^{2}`; `\dfrac`≡`\frac`; styling stripped; sub-expression tokens |
| `tests/modules/nfr/search/test_text_fields.py` | unit | Folding of ি/ী, ু/ূ, ণ/ন, শ/ষ/স; Banglish "nioton er sutro" matches "নিউটনের সূত্র"; digit normalisation |
| `tests/modules/nfr/search/test_query.py` | db | Lexical hits; misspelt Bangla via trigram; Banglish query; maths query; filters (node with descendants, type, status, tenant null-only for public); pagination stable |
| `tests/modules/qb/test_selectable_contract.py` | contract | `get_versions(include_key=False)` never contains `answer_key`, explanations are present, rendered HTML present; DTO frozen |
| `tests/modules/test_authz_matrix_b2.py` | authorization | Every B2 admin route × roles and scopes (subject-scoped reviewer outside scope → 403) |
| `tests/regression/test_b1_still_green.py` | regression | The B1 auth flow smoke test still passes (imported fixtures) |
| `tests/load/search.js` (k6) | load (not CI) | 500-query mix on a 150,000-question synthetic bank: p95 < 300 ms on the replica-sized instance (v2 §7.1 gate, rehearsed fully in B4) |

---

## F. Build completion

### F.1 Acceptance criteria

1. All B2 endpoints in [14](14_api_contracts.md) exist, with the D-section contracts covered by API tests.
2. A pilot workflow on staging works end to end: import 200 questions (xlsx) → drafts → submit → blind verification by a second reviewer → publish → rendered and indexed → selectable through `qb.get_selectable_versions`.
3. Immutability: no API or SQL path (as `app_rw`) can modify a published version (tests).
4. A blind-verification author-equals-verifier attempt is rejected by both the service (403) and the database (check violation).
5. Unknown-rights questions cannot be published (service and DB).
6. Search: on the 2,000-question fixture bank, 95% of the 100 fixture queries (Bangla, Banglish, misspelt, maths) return the expected item in the top 10.
7. Rendering: 100% of the fixture TeX renders, or is recorded in `rendering_failures`; no worker crash.
8. Coverage ≥ 85% overall; ≥ 95% on `qb/internal/services/scoring.py`, `key_compare.py`, `status.py`, `cms/internal/services/verify.py`, `publish.py`, `transitions.py`, and `nfr/internal/search/math_canonical.py`.
9. `scripts/check.sh` is green, with no file over 200 lines (including the Node CLI) and no boundary violations.

### F.2 Deliverables

Code per §C.3; migrations `b02_01`–`b02_13`; the Node renderer; seed YAML for the pilot tracks; fixture import files; the updated OpenAPI snapshot; and the PR build report.

### F.3 Definition of done

[`21_definition_of_done.md`](21_definition_of_done.md).

### F.4 Manual verification checklist

- [ ] Load the SSC 2028 Physics tree; view it in Bangla and English via the public tree API.
- [ ] Create one question of each of the 10 types through the API; preview renders Bangla and maths correctly.
- [ ] Verify blind as a second reviewer; confirm the author's key was not visible.
- [ ] Publish and confirm `selectable` turns true within 60 s.
- [ ] Search "nioton" and "নিউটন" and `1+2x+x^2`, and find the seeded items.
- [ ] Triage a seeded error report and see the SLA ages.

### F.5 Exit criteria before Build 3

F.1 holds; the PR is merged; staging is migrated; the proposed additions are accepted or rejected in 01 and 14; and the content team has signed off the import template, or the build report lists the open change requests.

---

## Proposed additions (accepted)

All items below were reviewed during integration and **accepted**. Redis keys are in [`01`](01_database_design.md) §3.17, columns and constraint values in 01 §3/§4, and error codes in [`14`](14_api_contracts.md) §1.5. Cross-module functions listed here are part of the owning module's public API (`__init__.py`).

| Kind | Item | Reason |
|---|---|---|
| Column value | `qbank.import_jobs.kind` also allows `tree` | Reuse the import pipeline for TAX tree imports (`/v1/admin/nodes:import`) |
| Column | `curriculum.tracks.bilingual_required boolean DEFAULT false` | Enforce both languages per track (QB-05) |
| Redis key | `qv:{question_version_id}:{lang}:{k|nk}`, 7 days | Hot read cache for immutable versions (01 §5.11 session start) |
| Redis key | `tax:tree:{syllabus_version_id}:{updated_epoch}`, 1 day | Tree cache |
| Function | `qb.set_index_status` (public) used by NFR search | Keeps `question_versions` writes inside QB |
| Upload purposes | `import_file`, `tree_import`, `question_media` | Presign allow-list extension |

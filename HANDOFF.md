# Session handoff: backend and database implementation plan

**Date:** 2026-11-27 · **Branch:** `main` · **Last commit:** `f0978b7` "Add backend and database implementation plan in nine builds" (pushed to `origin/main`)

## 1. What was asked

The supervisor's master-plan prompt asked for a **planning-only** package. It covers the complete database design, then the backend in **exactly nine builds** covering all 180 IDs in `features.md` (93 P0, 67 P1, 20 P2). The output is 23 documents in `docs/implementation/`, followed by an independent review, an executive summary, and a stop for supervisor approval.

The prompt also said what not to do:

- no backend code, models or migrations;
- no changes to the `backend/` skeleton;
- no frontend work, dependency installs or deployments;
- no requirements beyond the documented ones;
- no more than nine builds;
- no capacity claims without a benchmark.

The database comes before the backend, and the backend and database come before the frontend.

The user added two things during the session:

- **Money:** stored as integer poisha (the user picked the recommended option).
- **Social sign-in:** "add login with google and facebook this types of things".

## 2. What was completed

- **The full package was written:** `docs/implementation/README.md` and documents `00` to `21`, about 18.9k lines in total.
- **The independent review was applied.** It took seven viewpoints (architect, DBA, FastAPI, security, SRE, QA, engineering manager) and produced 32 findings. Every finding was fixed and recorded in `00_architecture_review.md` Part B.
- **All mechanical checks passed:**
  - 180/180 feature IDs are mapped, with matching priorities.
  - All 278 tables appear in the migrations, the ERD and the §4 specifications.
  - Every endpoint in the build documents is in the `14` index.
  - Mermaid syntax lint found 0 issues.
  - Every planned file is estimated at 200 lines or fewer.
  - The module graph is acyclic.
- **Pushed:**
  - Root `README.md` gained a link to `docs/implementation/README.md`.
  - Commit `f0978b7` was pushed to `main` after the user asked.
- **`backend/` was not touched.**

## 3. Files created or modified

| Path | Change |
|---|---|
| `docs/implementation/README.md` | New. Reading order, the nine builds at a glance, engineering rules, how to use a build document in a new session. |
| `docs/implementation/00_architecture_review.md` | New. Part A: 20 inconsistencies and corrections, supervisor decisions S-1 to S-8. Part B: 32 review findings with resolutions, S-9 to S-12. |
| `docs/implementation/01_database_design.md` | New, about 7.5k lines. Conventions, 278 tables across 16 schemas (157 of them created in B1–B6 for P0), per-table specifications, Redis keyspace, transactions, races R1 to R21, idempotency, retention, pooling, backup, partitioning, growth. |
| `docs/implementation/02_database_erd.md` | New. 17 Mermaid ER diagrams: an overview plus one per schema. |
| `docs/implementation/03_database_migration_plan.md` | New. About 103 Alembic migrations named `bNN_MM_slug`, plus seeds and the expand/contract approach. |
| `docs/implementation/04_backend_master_plan.md` | New. Layout, layering, module communication rules, the dependency graph (17 nodes, 39 edges), the build graph, effort and calendar. |
| `docs/implementation/05_build_01.md` … `13_build_09.md` | New. Sections §0 and §A to §F per build: overview, database, files, APIs, tests, exit criteria. |
| `docs/implementation/14_api_contracts.md` | New. Conventions, error codes, an index of 453 operations (B1 47, B2 38, B3 57, B4 22, B5 35, B6 56, B7 62, B8 79, B9 57). |
| `docs/implementation/15` … `21` | New. Testing and quality, traceability (180/180), scalability, security, DevOps, risk register (RK-01 to RK-42), definition of done. |
| `README.md` (root) | One link line added. |
| `HANDOFF.md` | This file. Not committed yet. |

Outside the repo:

- **Memory notes:**
  - `student-app-backend-skeleton.md`: money decided as integer poisha.
  - `student-app-social-login.md`: new.
  - `MEMORY.md` index updated.
- **Plan file:** `~/.claude/plans/pasted-content-id-a9f1-backend-crispy-liskov.md`.

## 4. Key decisions

### Stack and structure

- **Runtime and data stores:**
  - A FastAPI modular monolith on Python 3.13 and PostgreSQL 17, with pgvector, pg_trgm, ltree and btree_gist.
  - A general Redis, plus a **dedicated exam Redis** (`noeviction`, AOF, Multi-AZ).
  - A Postgres job queue using `SKIP LOCKED`. SQS is used only for exam answers.
  - The outbox feeds a Parquet event log on S3. There is no ClickHouse at P0.
  - A Cloudflare edge Worker serves exam time and key release.
- **Deployables:** `api`, `workers`, `ai-gateway`, `exam-ingest`, `exam-consumers`, and `realtime` (B9).
- **Modules:** 16 server modules (OFF is client-only).
  - The public surface of each module is `__init__.py` plus `contracts/`. Everything under `internal/` is private.
  - Repositories are plain async functions, not classes. Services own transactions. Routers are thin.
- **Boundary checks:**
  - A compact `.importlinter` enforces the layers and the exam-ingest no-Postgres contract.
  - `scripts/check_boundaries.py` (using grimp) blocks imports of another module's `internal/`.
  - Allowed module edges are listed in `scripts/module_edges.toml`.
- **Authorization:** `core.security.require` uses token claims plus the `auth:grants` cache, so modules never import AUTH.
- **Dependency rules that keep the graph acyclic:**
  - OPS and PLAN are near-leaves.
  - Rescoring is a PRAC job triggered by `correction.created`.
  - INST uses AI only through `ai.request_marking` and `ai.get_drafts`.
  - Deletion goes through the `user.deletion_requested` event.
  - PRAC consumes `exam.scored`.

### Database

- **Conventions:** UUIDv7 ids, UTC `timestamptz`, explicit Dhaka dates. Money is a `bigint *_poisha` column. Status values use text CHECK constraints, not ENUMs. Every table has `tenant_id` from day one, with RLS added in B8.
- **Cross-schema foreign keys** may point only at `identity.users` and immutable content or reference rows, with `ON DELETE RESTRICT`.
- **Partitioning:**
  - `attempt_answers` and `reward_transactions`: hash on `user_id`, 64 partitions, no foreign keys.
  - `exam_answer_batches` and `exam_answers_latest`: monthly range partitions on `exam_starts_on`.
  - `outbox` and `processed_events`: daily.
  - AI, notification, SMS, email and audit logs: monthly.
- **Connections:** PgBouncer in transaction mode, with asyncpg `statement_cache_size=0` or PgBouncer ≥ 1.21.
- **Answer transaction:** answer, notebook and progress first; then GAM and ANL inside a savepoint; then the outbox row. All of it is one transaction.

### Exam answer path

- `seq` is the per-attempt batch number, and ingest acknowledges only `acked + 1`.
- `acked_through` is kept in the exam Redis, in every SQS message and in the submit marker.
- Contiguity is checked against the maximum of all that evidence.
- Closing is two-phase, timed by the maximum attempt `ends_at`.
- Seats use a `registered_count` conditional counter.
- Attempts can have the status `voided`.

### Events and gamification

- The consumer jobs are batched, with at most 500 events per job and dedupe per (consumer, relay batch).
- Leaderboards are updated by a Lua script.
- The relay polls every 250 ms while busy and every 1 s when idle. The lag target is p95 ≤ 5 s.
- Reward keys are canonical and live in `gam/contracts/reward_keys.py`.
- Streaks are settled lazily, with a provisional/final 72 h window from B7 (decision S-9).

### Sign-in

- **Providers:**
  - **Google (B1):** ID token verified against the JWKS.
  - **Facebook (B1):** verified through the Graph API `debug_token`.
  - **Apple (B8):** JWKS plus token revocation.
  - **Email and password (B8):** uses the same session model.
- **Mechanics:** a `SocialProvider` protocol, a single-use nonce endpoint, and an `identity.external_identities` table.
- **Linking:** automatic only for a verified Google email that matches a verified email on file. Facebook never auto-links.
- **Age and consent:** date of birth is collected before an account is created. Facebook has a 13+ age gate.
- **Meta platform callbacks:** data deletion and deauthorise, both audited.
- **Staff:** OIDC single sign-on with MFA in B1.

### Payments, AI and money

- **bKash state machine:** `initiated → execute_requested → executed | execute_unknown → captured`. A `duplicate_captured` payment is refunded automatically.
- **Coupons** are redeemed inside a SAVEPOINT.
- **AI tutor:**
  - An 8-stage pipeline with a canonical cache that holds no personal context.
  - Responses stream over SSE one sentence at a time, after moderation. Responses for under-18s and free-form answers are buffered.
  - `exam.is_user_exam_locked` is the authority for the exam lock.
- **Money:** integer poisha everywhere. Decimal conversion happens only inside payment adapters.

### Builds and effort

| Build | Name | Effort (person-weeks) |
|---|---|---|
| B1 | Platform foundation, identity and safety | 10–13 |
| B2 | Curriculum, question bank and content workflow | 10–14 |
| B3 | Learning loop and gamification core | 12–16 |
| B4 | AI tutor platform | 13–18 |
| B5 | Live exam engine | 14–19 |
| B6 | Teacher-checked marking, commerce and operations (**all P0 complete**) | 12–16 |
| B7 | P1: personalised learning and engagement | 16–22 |
| B8 | P1: institutions, parents, exam integrity and growth | 24–32 |
| B9 | P2 expansion and scale certification (all 180 IDs) | 26–36 |

- **Build order:** B1 → B2 → B3 → {B4, B5 in parallel} → B6 → B7 → B8 → B9. B8 also depends directly on B6.
- **Total:** 138–186 person-weeks, about 44–57 calendar weeks.
- **P0 alone:** 71–96 person-weeks, about 24–31 weeks.

### Quality gates

- Ruff, mypy strict, pytest with HTTPX, pytest-cov and pre-commit all run from B1.
- Coverage is at least 85% overall and 95% on critical paths.
- Every handwritten file is at most 200 lines.
- `scripts/check.sh` is the single gate command.

## 5. Open items and next steps

1. **Supervisor approval (blocking).** The supervisor needs to review decisions S-1 to S-12 in `docs/implementation/00_architecture_review.md`, sections A.5 and Part B. Notable ones:
   - allowing the week-2 device spike as throwaway work;
   - the rolling 24 h repeat window;
   - the cross-user answer-id gate restated as "never returns another user's data";
   - the `repositories/` folder added to the module template;
   - the streak finalisation window (S-9).
2. **Evidence still to check.** Some statements are tagged `[Needs evidence]` and should be checked before the build that depends on them. One example is the current wording of Apple's guideline 4.8 for Sign in with Apple.
3. **After approval, start Build 1 in a new session.** Give the coding agent these documents:
   - `docs/implementation/README.md`
   - `04_backend_master_plan.md`
   - `05_build_01.md`
   - the `01` and `14` sections named in that build document

   The agent implements B1 only, runs `scripts/check.sh`, verifies the exit criteria in section F, and stops.
   **B1 evidence checked on 2026-11-27, with results written into the plan:**
   - Facebook `FACEBOOK_GRAPH_VERSION` is pinned to `v27.0` (`05_build_01.md`).
   - `public_profile` and `email` need no App Review. Before launch, switch both to Advanced Access, put the app in Live mode, and complete the Data Use Checkup (`05_build_01.md`).
   - The breached-password check uses the HIBP range API (`18_security_architecture.md`).
   - The Play Integrity quota is 10,000 requests per day per app, and the Cloud project must be linked (`18_security_architecture.md`).

   **Still open for B1:**
   - Whether Facebook Business Verification is needed. Check this in the App Dashboard.
   - ClamAV or a managed malware scanner.
   - The AI provider contract check.
4. **Committed.** `HANDOFF.md` was committed with the evidence updates. It has not been pushed.
5. **Do not start implementing anything until the supervisor approves.** Frontend work waits until all nine builds are done, apart from the throwaway spike if it is approved.

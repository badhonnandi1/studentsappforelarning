# 21 · Definition of done

**Date:** 2026-11-27 · This applies to every change, build and release across Builds 1–9. Tooling details: [`15_testing_and_quality_standards.md`](15_testing_and_quality_standards.md). Release mechanics: [`19_devops_and_deployment.md`](19_devops_and_deployment.md). Traceability: [`16_feature_traceability_matrix.md`](16_feature_traceability_matrix.md).

---

## 1. Done for any change (every PR)

| # | Criterion | How it is checked |
|---|---|---|
| D1 | `ruff format --check` and `ruff check` report zero issues | `scripts/check.sh`, pre-commit, CI |
| D2 | `mypy --strict` reports zero errors over `src`, `tests` and `migrations` | `scripts/check.sh`, CI |
| D3 | All tests pass with `filterwarnings=error`. No skipped test without a linked issue and an expiry date. | CI |
| D4 | Coverage ≥ 85% overall and ≥ 95% on critical paths (`scripts/check_coverage_paths.py`). Coverage never drops by more than 0.5 points in a PR without a stated reason. | CI |
| D5 | No handwritten file exceeds 200 physical lines (`scripts/check_file_length.py`). Generated files are exempt only if listed in the approved allow-list. | pre-commit, CI |
| D6 | Module boundaries hold: `lint-imports` (layers, exam-ingest isolation) and `scripts/check_boundaries.py` (no cross-module `internal` imports, no cycles) | CI |
| D7 | Migrations: reviewed by a second engineer. `alembic upgrade head` and `alembic downgrade -1` run on a fresh database. `alembic check` shows models equal migrations. Each migration is under 200 lines and expand-only unless it is the planned contract step. | CI + review |
| D8 | The OpenAPI snapshot (`backend/openapi.json`) diff is reviewed. Breaking changes follow `14` §1.1. Every new endpoint already exists in `14` §3. | CI + review |
| D9 | Security checklist (§5) answered in the PR. Secrets only in the secret store. gitleaks clean. | pre-commit, review |
| D10 | New paths have structured logs (no PII, tokens or answer keys), metrics (latency histogram, error counter) and, where user-facing, an alert or dashboard panel | Review |
| D11 | Docs updated: the build document checkboxes, `01` and `14` if names changed, a runbook entry for any new failure mode | Review |
| D12 | Performance budget respected for the touched path (`17` §targets). Hot-path queries come with `EXPLAIN (ANALYZE, BUFFERS)` output in the PR description. | Review; perf tests where marked |
| D13 | `pip-audit` and the Trivy image scan report no high or critical findings | CI |
| D14 | The PR title and description follow `19` (Conventional Commits; linked build and feature IDs) | Review |

## 2. Done for a build

A build is done when every item below is true. It is then committed to `main` through a reviewed PR, tagged `build-NN`, and deployed to staging.

1. Every feature ID listed in the build document's section A is implemented to its acceptance criteria (section F), and `16` shows the ID's primary build as this build.
2. Every table in section B exists through migrations, with all its constraints and indexes. The partitioning required by `01` §1.2 is present. Seed and reference data is loaded by an idempotent script.
3. Every endpoint in section D is implemented with its request and response schema, auth, validation, errors, rate tier and idempotency. API tests cover each endpoint's success path, auth failure, authorization failure (another user's resource) and validation failure.
4. Section E test categories are present: unit, integration, API, database, authorization, edge cases, concurrency (where the build lists races from `01` §5.2), and failure and recovery.
5. All global gates in §1 pass on the build branch and on `main` after merge.
6. Previously delivered builds' test suites still pass unchanged (regression). Any change to an earlier contract follows expand, migrate, contract.
7. The manual verification checklist in section F has been executed on staging and the results recorded in the PR.
8. Red risks in `20` tied to this build are mitigated, or waived in writing by the supervisor.
9. The build report (PR description) lists: features delivered, tables, endpoints, test counts, coverage (overall and critical paths), measured performance numbers, known limitations and new risks.
10. **Stop rule (§6) observed.**

### 2.1 Per-build exit checklist template

Copy this into the build PR:

```markdown
## Build NN exit checklist
- [ ] Section A feature IDs implemented: <list>
- [ ] Section B migrations applied on a fresh DB; downgrade -1 tested; `alembic check` clean
- [ ] Section D endpoints implemented; OpenAPI diff reviewed; all routes present in 14 §3
- [ ] Section E tests: unit __ / integration __ / api __ / db __ / authz __ / concurrency __ / failure __
- [ ] Coverage: overall __% (≥85), critical paths __% (≥95)
- [ ] `scripts/check.sh` green (format, lint, mypy, boundaries, line limit, tests)
- [ ] pip-audit and Trivy clean
- [ ] Regression: previous builds' suites green, unchanged
- [ ] Performance: <targets from section F with measured values>
- [ ] Manual checklist (section F) executed on staging: <link to notes>
- [ ] Observability: logs, metrics, dashboards, alerts for new paths
- [ ] Runbook entries added: <list>
- [ ] Risk register updated (new risks, mitigations, red risks closed or waived)
- [ ] Docs updated (build doc, 01, 14, 16 if changed)
- [ ] Next build NOT started
```

## 3. Done for a release (P0 launch)

The P0 launch needs Builds 1–6 done, the frontend P0 done (outside these nine builds), and every v2 §8.2 gate passing. The table shows the first build in which each gate becomes testable, and where the automated suite lives.

| v2 §8.2 gate | Measure | Testable from | Evidence |
|---|---|---|---|
| Feature completeness | All 93 P0 IDs demonstrated against written acceptance tests | B6 (backend); full gate needs frontend | `16` primary builds B1–B6, plus the section F checklists |
| Content | ≥ 30 verified questions per topic on launch tracks; every published key two-person verified; no `source_rights = unknown` published | B2 | DB constraint tests plus a content report (`GET /admin/reports/coverage` in B7, or a B2 SQL report) |
| Learning-record integrity | Replay of 1M synthetic answers with 5% duplicates and reordering gives identical projections; sampled rebuild shows no differences | B3 | `tests/load/replay_1m.py`, `analytics.rebuild_audits` |
| AI tutor | Every row of v2 §4.8 passes (quality, maths, OCR, citations, latency, cost, safety, cache privacy) | B4 | `ai.eval_runs` with `gate_passed`, CI eval subset |
| Written marking | Each released subject passes the §4.10 gate with a published accuracy report; a teacher cannot read another batch | B6 | `ai.accuracy_reports`, `tests/modules/inst/api/test_batch_isolation.py` |
| Gamification | The §5.5 scenario plus 20 clock, duplicate and correction cases pass; no XP granted twice in the replay | B3 | `tests/modules/gam/unit/test_streak_scenarios.py`, replay test |
| Exam correctness | Fault injection: every acknowledged answer scored; contiguity catches every injected gap; merit identical across 3 replays | B5 | `tests/load/exam_fault_injection.js` (k6) + `exam_verify.py` report |
| Exam scale | Rehearsal at 25,000 (1.25 × launch cap) with zero acknowledged loss; provisional score within 5 s at p95 | B5 (20k harness), rehearsal before launch | Load-test report |
| Performance | Question-load gates 1–2 (client-side, frontend phase); API p95 < 300 ms at 6,000 concurrent users | B3 (API), B6 (full) | `tests/load/api_6k.py` report |
| Clients | v2 §6.6 rows on reference devices and the PWA | Frontend phase | Out of scope for B1–B9 |
| Payments | Sandbox and live test per gateway: duplicate webhook, missing webhook, refund, reconciliation mismatch | B6 | `tests/modules/pay/integration/*`, sandbox run log |
| Security and privacy | Another user's replayed answer id never returns their data (restated, `00` §2.1); cache-privacy test; pen test with no open high or critical; minors' privacy checklist; restore drill | B3 (id scope), B4 (cache), B6 (pen test, restore) | Test suites, pen-test report, drill record |
| Operations | Dashboards, alerts and runbooks for exam day, payment outage and AI outage; on-call staffed | B6 | `19` runbooks, alert rules in code |

## 4. Code review checklist

Reviewers tick these explicitly in the review:

- [ ] **Placement:** the code is in the right module, and business logic sits in services, not routers. Repositories are functions; there are no new classes for services or repositories.
- [ ] **Transactions:** one write transaction per request unless documented. No provider or network call inside a transaction. Savepoint only where `01` §5.1 says so.
- [ ] **Idempotency:** POSTs follow `14` §1.6. Background handlers write `processed_events` in the same transaction.
- [ ] **Concurrency:** every race listed in `01` §5.2 for the touched tables is handled by the stated control, with a test.
- [ ] **Authorization:** every by-id read or write checks ownership, a scoped grant or a relationship. 404, not 403, for resources the caller must not know exist.
- [ ] **Validation:** pydantic `extra="forbid"`. Bounds on strings, lists and numbers. Enum-like values checked.
- [ ] **Time:** `Clock` injected. UTC storage. Dhaka dates through `shared.dhaka_date`. No naive datetimes.
- [ ] **Money:** integer poisha only. No float. Decimal only inside provider adapters.
- [ ] **Data:** no PII or secrets in logs, events or error messages. PII columns encrypted and hashed.
- [ ] **Tenancy:** `tenant_id` filters on content, exams and institution data. Caches and search keys include the tenant.
- [ ] **Minors:** leaderboard, merit and certificate outputs expose only first name and institution.
- [ ] **Queries:** indexes exist for new query shapes. No N+1 queries. Pagination by cursor.
- [ ] **Tests:** they test behaviour, not lines. They include failure paths. No sleeps (frozen clock and fakes instead). No live external calls.
- [ ] **Files:** ≤ 200 lines, cohesive, named by subject. No `utils.py`.
- [ ] **Configuration:** no hardcoded quotas, rules, URLs or keys.
- [ ] **Observability:** logs, metrics and traces on new paths, plus alert thresholds where user-facing.
- [ ] **Docs:** `01`, `14` and `16` are updated in the same PR if names or shapes changed.

## 5. Security checklist (answered in each PR)

1. Does this change accept user input? Name the schema and its bounds.
2. Does it read or write another user's or tenant's data? Name the authorization check and its test.
3. Does it add a public (unauthenticated) endpoint? Justify it, and name its rate tier.
4. Does it call an external provider? Name the timeout, retry policy, circuit breaker and secret source.
5. Does it store a new kind of personal data? Name the encryption, retention entry in `01` §5.6, and deletion path.
6. Does it handle files? Name the content-type allow-list, size limit, private bucket, signed URL expiry, and malware or moderation scan where applicable.
7. Does it change auth, sessions or tokens? Request a security reviewer.

## 6. Stop rule

A build ends when its exit checklist (§2.1) is complete and the build PR is merged.

- The coding agent or engineer **must not** start the next build, pre-create its tables, or add its endpoints in the same branch.
- They **must not** modify the frontend, or create client code beyond test fixtures.
- Work discovered for later builds is written as a note in that build's document, under "Carry-over from Build NN", and as an entry in `20` if it is a risk.
- If an acceptance criterion cannot be met, the build stops at that point with a written report. It is not marked done.

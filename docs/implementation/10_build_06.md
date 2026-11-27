# Build 6 · Teacher-checked marking, commerce & operations (P0 complete)

| Item | Value |
|---|---|
| Build | 6 of 9 |
| Status | Planned (not started) |
| Depends on | Build 4 (AI provider layer, OCR, eval harness, prompt registry); Build 5 (exams, for exam fees and control-room parity); Build 3 (entitlements, quotas, notifications, PRAC self-mark path); Build 2 (CQ subparts and rubric points); Build 1 (consent, uploads, audit, roles) |
| Effort | 12–16 backend person-weeks ([`04`](04_backend_master_plan.md) §6.3) |
| Feature IDs | AI-07, AI-07a, AI-07b, AI-07c, AI-07d, INST-02a; PAY-03, PAY-04, PAY-05; OPS-01, OPS-02, OPS-03; NFR-06 (complete), NFR-06a (complete), NFR-08 (complete), NFR-10; NFR-07 (data requests) |
| Milestone | **All 93 P0 requirements implemented on the backend.** Live-exam cap stays at 20,000 until the 25k rehearsal passes (§C.1 step 20). |

---

## 0. How to run this build

1. **Read, in order:**
   - [`README.md`](README.md)
   - [`04_backend_master_plan.md`](04_backend_master_plan.md)
   - this document
   - [`01_database_design.md`](01_database_design.md):
     - §3.15 (`institution` B6 tables)
     - §3.12 (`marking_jobs`, `gradings`, `grading_parts`, `accuracy_reports`)
     - §3.14 (`commerce` B6 tables)
     - §3.5 (`banners`, `notices`)
     - §3.2 (`data_requests`)
     - §5.1–§5.3 (payment capture, refund, R9–R11, R19)
     - §5.6 (deletion)
   - [`14_api_contracts.md`](14_api_contracts.md) §3.9, §3.13, §3.16, and the B6 rows of §3.2
   - [`18_security_architecture.md`](18_security_architecture.md)
   - [`system-design-v2.md`](../system-design-v2.md) §4.10, §7.2, §7.4, §8.2, §8.5
   - [`product-strategy.md`](../product-strategy.md) §4–§5 (marking method and gates)
2. **Preconditions:**
   - `main` is green; B4 and B5 exit criteria are met.
   - Sandbox credentials exist for bKash and the aggregator ([Needs evidence]: merchant onboarding lead time). Without them the adapters are built against recorded sandbox fixtures and the live sandbox test is deferred, recorded in the PR.
   - A Google Play test track and service account are available, or recorded fixtures.
3. **Branch:** `build/06-marking-commerce-ops`.
4. **Commands:**
   - `scripts/check.sh`
   - `uv run pytest -m eval tests/modules/ai/eval/marking`
   - `uv run pytest -m concurrency tests/modules/pay`
   - `uv run python -m app.modules.ai.evalcli marking --set <subject>` (the accuracy run)
5. **Stop rule.**
   - Stop at §F. This build marks P0 backend complete.
   - Do not start P1 features. Batches here are minimal (INST-02a); workspaces and RLS are B8.
   - No frontend work.

---

## A. Overview

| Item | Detail |
|---|---|
| Name | Teacher-checked marking, commerce & operations |
| Objective | Ship the launch differentiator: AI-drafted, teacher-checked marks for handwritten CQ answers with published accuracy. Ship payments that are correct under duplicate and missing webhooks, refunds and reconciliation. Ship the admin console APIs, banners, notices and helpdesk integration. Complete the security, content protection, observability and recovery work the v2 §8.2 gates need. |
| Business value | The product position ([`product-strategy.md`](../product-strategy.md)) and revenue. P0 is complete. |
| Technical value | Exercises the AI layer on a second, higher-stakes workload with its own gate; payment state machines; the first tenant scoping (batch as tenant); release-gate evidence. |
| Modules | AI (marking pipeline, accuracy), INST (teacher approval, batches, tasks, submissions), PAY (orders, payments, refunds, coupons, referrals, invoices, reconciliation, store purchases), OPS (console APIs, banners, notices, helpdesk), AUTH (data requests, admin user APIs), NFR (crawl detection, canaries, SLOs), PLAN (receipts and notices), GAM (attempt XP for written answers). ANL takes no part here: the `marking.teacher_checked` event is consumed into mastery in B7. |
| Complexity | 4/5 |
| Effort | 12–16 pw |

**Features**

| ID | Delivered |
|---|---|
| AI-07 | Photo (or typed) written answers per CQ part, inside batch tasks |
| AI-07a | CQ rubric marking at launch (ক/খ/গ/ঘ or 3-part subjects, per `cq_subparts`). BCS and English writing rubric types are a later extension ([`11_build_07.md`](11_build_07.md)). |
| AI-07b | Draft output: score, rubric breakdown, evidence quote per mark, missing points, model answer reference, rewrite suggestions |
| AI-07c | Teacher review queue in triage order; the teacher's mark is final, stored as a new grading; "teacher checked" or "practice estimate" labels |
| AI-07d | Accuracy reports per subject and part (QWK, exact, within-one, bias, MAE, intervals), published in the app and re-measured on every model or prompt change |
| INST-02a | Ops-approved teacher accounts; batches with join codes; guardian consent before an under-18 student joins; written tasks; answer collection |
| PAY-03 | bKash (create, execute once, query, IPN through SNS); one aggregator (SSLCommerz or aamarPay) for Nagad, Rocket, Upay and cards; Google Play Billing verification and RTDN. Apple IAP comes with iOS in B8. |
| PAY-04 | Coupons (once per user), referral credits ledger, gapless invoices, PDF and SMS receipts |
| PAY-05 | Full and partial refunds with credit notes; daily reconciliation at 03:00 Dhaka (API or settlement upload); webhook retries and the pending-order sweeper; failed-payment recovery |
| OPS-01 | Admin console APIs: user lookup, subscriptions and entitlements, manual grants, refunds, suspension, data requests |
| OPS-02 | Bought helpdesk: signed widget identity token, FAQ and call or WhatsApp links from config |
| OPS-03 | Banners and notices (blog and SEO live on a static site, per C19) |
| NFR-06 | OWASP API Top 10 review checklist, dependency and container scans enforced, pen-test readiness pack |
| NFR-06a | Per-account distinct-question limits, sequential-crawl detection, canary questions |
| NFR-08 | SLOs and burn-rate alerts for the 4 journeys (sign-in, practice answer save, paper and key fetch, exam ack) |
| NFR-10 | Restore drill procedure, automated and timed; cross-region snapshot copy verified |
| NFR-07 | Support-driven export and deletion with anonymisation within 30 days |

**Risks and blockers**

| Risk | Mitigation |
|---|---|
| D9: no subject passes the marking gate | The pipeline is built regardless. Release per subject is a data flag (`accuracy_reports.gate`). If none passes, AI drafts stay off, teachers mark from blank (queue still useful), and the product decision returns to P1 (v2 D9). |
| Handwriting OCR quality unknown | Image vs transcript route is configurable per subject. Both are evaluated by `evalcli marking`. |
| bKash Execute and IPN details | Built from the linked bKash docs (v2 §7.2) and verified in sandbox; anything unverified stays marked [Needs evidence] in the adapter docstring and the risk register |
| Merchant onboarding delays | Adapters run against recorded fixtures; the live sandbox test is a deferred exit item with an owner |
| D2: Play Billing scope | Play verification is built; whether the Android app sells in-app is a product switch (`runtime_config.android_in_app_purchase`) |
| VAT (Mushak) invoices [Needs evidence] | `invoices.vat_poisha` and the template fields exist; the template changes once the accountant answers |

---

## B. Database

### B.1 Tables to create

| Migration | Tables | Notes |
|---|---|---|
| `b06_01_inst_teachers_batches` | `institution.teacher_approvals`, `institution.batches`, `institution.batch_members` | `batches.tenant_id = batches.id` at P0 (a batch is its own tenant). uq `join_code`; partial uq on approvals. |
| `b06_02_inst_tasks_submissions` | `institution.written_tasks`, `institution.written_task_items`, `institution.submissions`, `institution.submission_pages` | uq `(task_id, user_id, question_version_id)`; uq `(submission_id, page_no)` |
| `b06_03_ai_marking` | `ai.marking_jobs`, `ai.gradings`, `ai.grading_parts`, `ai.accuracy_reports` | `gradings` has partial uq `(submission_ref_type, submission_ref_id) WHERE is_final`; `CHECK (source IN ('ai_draft','teacher'))`; `CHECK (NOT is_final OR source = 'teacher')` |
| `b06_04_pay_orders_payments` | `commerce.orders`, `commerce.payments`, `commerce.provider_events`, `commerce.store_purchases` | uq `(provider, provider_txn_id)`, uq `(provider, provider_payment_id)`, uq `(provider, provider_event_id)`, uq `purchase_token_hash`; `CHECK (payable_poisha = amount_poisha - discount_poisha)` |
| `b06_05_pay_refunds_coupons` | `commerce.refunds`, `commerce.coupons`, `commerce.coupon_redemptions`, `commerce.referral_codes`, `commerce.referral_credits`, `commerce.price_points` | `CHECK (redeemed_count <= max_redemptions)`; coupon code stored normalised (upper, no spaces) |
| `b06_06_pay_invoices_recon` | `commerce.invoices`, `commerce.invoice_sequences`, `commerce.credit_notes`, `commerce.reconciliation_runs`, `commerce.reconciliation_exceptions` | uq `invoice_no`; uq `(provider, business_date)` |
| `b06_07_ops_content` | `ops.banners`, `ops.notices` | ix `(status, starts_at, ends_at)` |
| (none) | `identity.data_requests` already exists (created in B1, `b01_10`) | Add ix `(status, due_at)` in `b06_08_identity_data_requests_ix` if B1 did not |

### B.2 Tables modified

| Table | Change | Migration |
|---|---|---|
| `commerce.entitlements` | No DDL; new sources used: `payment`, `coupon`, `admin`, `referral` | — |
| `exam.registrations` | Uses `order_id` for paid exams (already a column) | — |
| `platform.runtime_config` | Seed keys `payments_enabled`, `android_in_app_purchase`, `support_links`, `helpdesk_widget` | data migration `b06_09_seed_config` |

### B.3 Relationships

- `batches.teacher_user_id`, `batch_members.user_id`, `submissions.user_id` → `identity.users` (FK).
- `written_task_items.question_version_id` and `submissions.question_version_id` → `qbank.question_versions` (FK; CQ type enforced in the service).
- `gradings.submission_ref_id` is a plain uuid with `submission_ref_type` (`inst_submission` now; `exam_written_answer` in B8). AI does not FK into INST and **never calls INST**. INST pushes everything AI needs in a `MarkingRequest` DTO (R-03), and integrity is checked by INST's orphan check.
- `grading_parts.subpart_id` → `qbank.cq_subparts`, and `rubric_point_id` → `qbank.rubric_points` (FK, immutable content).
- `payments.order_id` → `orders` (FK); `refunds.payment_id` → `payments`; `invoices.order_id` → `orders` (uq); `credit_notes.refund_id` → `refunds` (uq).
- `orders.product_id` → `commerce.products`; `coupon_redemptions.order_id` → `orders`.

### B.4 Transaction and integrity requirements

| Operation | Rule |
|---|---|
| Join batch | Tx: check consent (`auth.has_guardian_consent(user)` if minor, else 403 `consent_required`); insert member (PK prevents duplicates); audit if staff-initiated. |
| Submit | Tx: all pages present (`page_no` 1..n contiguous) and quality checks passed; status `submitted`. Then INST calls `ai.request_marking(session, MarkingRequest)`: submission id, tenant id, page storage keys or typed text, and the rubric (fetched by INST through `qb.get_cq_rubric`). AI stores `marking_jobs` and enqueues `ai.mark_submission` with `dedupe_key = submission_id` in the same Tx. Dependency direction: INST → AI only. |
| Drafting | Each run writes a new `gradings(source='ai_draft', run_no)` + parts in its own Tx. `marking_jobs` is updated with disagreement and triage at the end. Drafts are never updated. |
| Teacher mark | INST's review service calls `ai.record_teacher_marks(session, submission_id, parts, teacher_id)`. In one Tx: lock the `marking_jobs` row; **first** `UPDATE gradings SET is_final = false` on any existing final (re-mark); **then** insert `gradings(source='teacher', is_final=true, supersedes_id=<previous final or latest draft>)` + parts. The non-deferrable partial unique index allows only this order (R-19). Then `submissions.status='teacher_checked'` and outbox `marking.teacher_checked` (consumed by GAM attempt XP now and by the ANL mastery consumer from B7, R-28). |
| Release | Tx: submissions → `released`; outbox per student; notifications through PLAN. |
| Payment capture | v2 §7.2 and 01 §5.1: `SELECT orders … FOR UPDATE`; verify provider status and amount; payment `captured`; entitlement + events; invoice number from `invoice_sequences` (row lock); outbox `payment.captured`; the order is `paid`. All in one Tx. **If the order is already `paid`** and a second, different provider transaction succeeded (the user paid twice), the new payment is recorded as `duplicate_captured`, a `reconciliation_exceptions` row (`kind='duplicate_payment'`) is opened, and the job `pay.refund_duplicate` refunds it automatically (status `refunded`, credit note). The money is never kept silently (R-08). |
| Webhook | Tx 1: insert `provider_events` (uq dedupe; a duplicate gives 200 no-op). Job `pay.process_provider_event` then runs a verify-then-capture. |
| Refund | Tx 1: refund `requested` (audited). Provider call outside the Tx. Tx 2 on confirmation: refund `completed`; entitlement shorten or revoke (only the refunded product's entitlement); events; credit note; order `refunded` or `partially_refunded`; outbox `entitlement.changed`. |
| Coupon redemption | Inside the capture Tx, in a **SAVEPOINT** (`session.begin_nested()`): conditional `UPDATE coupons … WHERE redeemed_count < max_redemptions RETURNING`, then insert the redemption (PK `(coupon_id, user_id)`). On a unique violation or zero rows updated, roll back **to the savepoint only**, log, and open a reconciliation exception (`kind='coupon_over_redeemed'`). Capture then proceeds at the price validated at order creation **[Rule]**. Without the savepoint, the unique violation would abort the whole capture transaction (R-19). |
| Referral credit | Ledger insert with `idempotency_key = referral:{order_id}`. |
| Data deletion | Event-driven, so AUTH imports no other module (R-03). On staff approval AUTH writes the outbox event `user.deletion_requested{request_id, user_id}` and sets `data_requests.module_status = {module: "pending"}` for every registered module with user data. Each module's consumer anonymises its own data in its own Tx (idempotent via `processed_events`) and emits `user.deletion_completed{request_id, module}`. AUTH's consumer marks that module done, and completes the request when all are done; it alerts at 25 days if any module is pending. Files are deleted by each module's job after commit. Export works the same way: `user.export_requested` → per-module `user.export_part_ready{module, object_key}`, then AUTH assembles the bundle. |

---

## C. Backend implementation

### C.1 Steps in dependency order

1. **Settings:**
   - `bkash_base_url`, `bkash_app_key`, `bkash_app_secret`, `bkash_username`, `bkash_password`, `bkash_sns_topic_arn`
   - `aggregator_kind` (sslcommerz, aamarpay), `aggregator_store_id`, `aggregator_secret`
   - `google_play_package`, `google_play_service_account_json`
   - `invoice_pdf_template`, `helpdesk_kind`, `helpdesk_secret`
   - `marking_route` (image, transcript), `marking_runs` (default 2), `marking_model_tier` (top)

   The prod validator requires all enabled providers' secrets.
2. **INST minimal** (INST-02a):
   - teacher application and approval (ops);
   - batches with join codes (8 characters, Crockford base32, expiry);
   - join and leave;
   - written tasks with CQ items;
   - submissions and pages (presigned upload purpose `submission_page`; client quality report stored; server re-check of size and type);
   - the batch-scoped access helper `inst.can_access_submission(actor, submission)` (used only inside INST).
3. **AI marking pipeline** (AI-07 to AI-07c). Public API: `ai.request_marking(session, MarkingRequest)`, `ai.get_drafts(submission_id) -> list[GradingDTO]` and `ai.record_teacher_marks(...)`. AI never imports INST.
   - `ai.mark_submission` job: the rubric and the page keys come from the stored `MarkingRequest`, not from a call back into INST or QB.
   - Choose the route:
     - **image:** pages go straight to the vision model with the rubric;
     - **transcript:** first a word-for-word transcript (a "do not correct" prompt), then marking. Digits are checked separately: numbers are extracted and compared across runs.
   - The student text goes in a `<student_answer>` data block; instruction-like text sets `flags=['instruction_like']`.
   - Per part: marks ≤ part marks, plus `evidence_quote` (must be a substring of the transcript or OCR text, else the flag `evidence_unverified`), `missing_points`, `rewrite_suggestions`, `model_answer_ref` (→ `cq_subparts.model_answer_*`).
   - Run `marking_runs` times. Triage priority goes up when any of these hold: disagreement > 1 mark in any part, OCR confidence < threshold, flags, or a total at a grade boundary (configured list).
   - On failure or timeout (10 min), the submission enters the queue unmarked (`triage_reasons=['draft_failed']`).
   - Cost via `ai.record_usage(route='marking')`; the routing ceiling does not apply (v2 §4.10), but a separate `marking_per_month` quota from `quota_policies` does.
4. **Teacher review** (AI-07c), implemented in **INST** (`inst/internal/services/review_queue.py`): the queue ordered by `triage_priority DESC, submitted_at`. Triage values come from `ai.get_drafts`, and INST batch-scopes the list before asking. Detail shows page URLs (presigned, 5 min), drafts and evidence. Marking calls `ai.record_teacher_marks`; then the task is released.
5. **Student view:**
   - The label is "teacher checked" when a final teacher grading exists.
   - "practice estimate" is shown only when the subject's latest accuracy report gate is `practice_estimate` and the student is outside a batch. That self-practice path is behind a flag; the default is off.
   - Written answers earn attempt XP only, from the GAM consumer of `marking.teacher_checked` (key built by `gam.contracts.reward_key`, reason `written_attempt`).
   - Teacher-checked marks feed mastery only from **B7**: `analytics.mastery_state` is created there, and the ANL consumer of `marking.teacher_checked` is added in B7 (R-28). B6 only emits the event, which is retained in the S3 log so that B7 can backfill. The marks never enter merit.
6. **Accuracy reports** (AI-07d):
   - `evalcli marking --set <subject>` runs the double-marked set (≥ 400 answers) and computes per part and total: QWK, exact and within-one agreement, MAE, bias in SD units, the share sent to the teacher, and slices by handwriting quality, phone and mark band.
   - Intervals come from a cluster bootstrap over students and questions (1,000 resamples).
   - The gate is decided as `teacher_review` (QWK ≥ 0.70, ≤ 0.10 below teacher–teacher, |bias| ≤ 0.15 SD), `practice_estimate` (also QWK ≥ 0.80) or `failed`.
   - Staff publish the report. A model or prompt change invalidates the subject's release flag until a new report passes, checked by `prompt_versions` vs `accuracy_reports.prompt_version`.
7. **PAY provider protocol:** `PaymentProvider` with `create(order) -> Redirect|SdkPayload`, `execute(payment)`, `query(payment)`, `refund(payment, amount)`, `parse_event(request) -> ProviderEvent`, `fetch_settlement(date)`.
8. **bKash adapter:**
   - Token grant and refresh (cached in Redis, a proposed key).
   - Create payment.
   - **Execute** once. Under the order lock, move `initiated → execute_requested`, set `execute_requested_at`, and **commit before** calling bKash Execute. Any retry finds `execute_requested` and never calls Execute again. It resolves only by **query**. A timeout or crash after the commit leaves `execute_requested`/`execute_unknown`, and the sweeper resolves it by query (R-08).
   - Query.
   - Refund.
   - The SNS handler: verify the SNS signature (cert URL host allow-list `sns.<region>.amazonaws.com`), auto-confirm the `SubscriptionConfirmation`, parse the notification.
   - IPNs cover successful payments only; status queries remain the source of truth.
9. **Aggregator adapter:** session init, IPN with hash verification, a validation API call before capture, refund API.
10. **Google Play:**
    - Verify the purchase token through the Android Publisher API (service account).
    - Check `purchaseState`, `acknowledgementState` and `obfuscatedExternalAccountId == user_id hash`.
    - Capture into the same transaction.
    - Acknowledge within 3 days (job).
    - RTDN via a Pub/Sub push endpoint with JWT verification.
11. **Order service:**
    - Create: product price from the current `price_points`, coupon validation, `payable_poisha`, `expires_at = now + 24h`.
    - Callback handling, which triggers verify.
    - Verify-then-capture.
    - The sweeper job `pay.sweep_pending` at +1, +5, +15 and +60 min after creation, then expiry at 24 h (PAY-05).
    - The order status endpoint.
12. **Coupons, referrals and invoices:**
    - Coupons: admin CRUD, validate, redeem in capture.
    - Referral credit on the referred user's first captured order; spending credits is P1 (PAY-07 attribution is B8), and credits are ledger-only here.
    - Invoices: gapless number per fiscal year (July–June in Bangladesh **[Assumption]**), PDF rendered by the worker (WeasyPrint with bundled Bangla fonts), SMS receipt via `plan.send_sms(template='receipt')`.
13. **Refunds:**
    - Admin full or partial refund with a reason (audited).
    - Provider refund; on confirmation, the entitlement adjustments.
    - Partial-refund rule: shorten `ends_at` proportionally to `refund/payable` of remaining validity, or revoke if ≥ 100%.
    - The union-of-entitlements check continues access if another active entitlement covers the scope.
    - Unused AI credits refunded pro rata; a live-exam fee is refundable only before the exam starts (rule check).
    - Credit note.
14. **Reconciliation** (03:00 Dhaka daily): for each provider, fetch the settlement (API) or wait for an upload. Compare it with `payments` for the business date:
    - paid there, not captured here: capture and grant automatically, then notify the student;
    - captured here, missing or reversed there: suspend the entitlement and raise an exception;
    - amount or refund mismatches: raise an exception.

    Exceptions open past 48 h trigger an alert.
15. **OPS console APIs** (OPS-01):
    - user lookup by phone (hashed server-side) or email or id;
    - user detail aggregating AUTH, PAY, PRAC summary and EXAM attempts through public functions;
    - suspend (revokes sessions);
    - manual grant and revoke;
    - refunds;
    - the data request queue.

    Every write goes through `ops.audited`.
16. **Banners and notices** (OPS-03): CRUD with audience targeting (track, class, district, plan) evaluated server-side; learner endpoints cached 60 s per audience key.
17. **Helpdesk** (OPS-02): `/v1/support/config` from `runtime_config.support_links`; `/v1/support/widget-token` returns an HMAC/JWT identity token for the vendor widget (user id, first name, locale; no phone unless the user opts in).
18. **Data requests** (NFR-07). The table exists since B1, where Meta data-deletion callbacks already create rows. B6 adds the user and staff flows. Staff approve a request; then:
    - **Export:** `user.export_requested` event → each module's consumer writes its section to S3 and emits `user.export_part_ready` → AUTH assembles the JSON and CSV bundle and a signed URL valid for 7 days.
    - **Deletion:** `user.deletion_requested` event → each module's consumer anonymises its own data:
      - AUTH nulls PII and deletes external identities and devices;
      - PLAN deletes tokens;
      - AI deletes threads and photos;
      - INST deletes submission pages;
      - COM anonymises reports.

      Each module then emits `user.deletion_completed{module}`, and AUTH tracks this in `data_requests.module_status`. Pseudonymous learning and financial rows are kept (01 §5.6). Deletion and phone change need a step-up OTP (18 §1).

    Due 30 days; an alert at 25 days.
19. **NFR-06a completion:**
    - **Distinct-question limit:** `crawl:{user}:{hour}` HLL is updated on every question payload served (PRAC session fetch, review, search hits count as ids). Above 600 per hour, the API returns 429 `content_rate_limited` and raises a security event.
    - **Sequential-crawl detector job:** ids requested in taxonomy or creation order across sessions, flagged per user.
    - **Canary questions:** `qbank.questions` with `tags @> '{canary}'`, unique per cohort; a leak search runbook.
    - Media and papers keep short-lived signed URLs (B2/B5).
20. **Hardening for the P0 gates:**
    - SLO definitions and multi-window burn-rate alerts (1 h/5 m at 14.4×, 6 h/30 m at 6×) for the 4 journeys.
    - Synthetic checks from two Bangladeshi networks (vendor config in [`19`](19_devops_and_deployment.md)).
    - The pen-test readiness pack: OWASP API Top 10 mapping, an authz test matrix report, dependency and Trivy reports.
    - The restore drill script, timed: restore the latest snapshot into an isolated account, run verification queries, record RTO and RPO.
    - **The 25k exam rehearsal** (1.25 × the launch cap), run on the B5 harness; its pass is a launch gate.

### C.2 Folder changes

```
backend/src/app/modules/inst/{__init__.py, contracts/, internal/{models,repositories,services,schemas,routes,events}}
backend/src/app/modules/ai/internal/marking/        # pipeline files for written marking
backend/src/app/modules/ai/internal/evals/marking/  # accuracy computation
backend/src/app/modules/pay/internal/{providers/{bkash,aggregator,google_play}, orders, refunds, recon, invoices}/
backend/src/app/modules/ops/internal/{console, content, support}/
backend/src/app/modules/auth/internal/services/data_requests.py
backend/src/app/modules/nfr/internal/protection/
backend/prompts/marking-transcribe-v1.md, marking-score-v1.md
backend/templates/invoice_bn.html, invoice_en.html      # Jinja templates (≤ 200 lines each)
ops/runbooks/restore_drill.md, ops/slo/*.yaml          # referenced from 19
```

### C.3 Files

**INST (INST-02a)**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `inst/__init__.py` | `routers()`, `job_handlers()` (deletion and export consumers) | 40 |
| `inst/internal/services/review_queue.py` | Teacher queue and detail, using `ai.get_drafts`; mark through `ai.record_teacher_marks` | 140 |
| `ai/contracts/marking.py` | `MarkingRequest`, `GradingDTO`, `TeacherPartMark` DTOs (public) | 70 |
| `inst/internal/models/batches.py` | `TeacherApproval`, `Batch`, `BatchMember` | 90 |
| `inst/internal/models/tasks.py` | `WrittenTask`, `WrittenTaskItem`, `Submission`, `SubmissionPage` | 110 |
| `inst/internal/repositories/batches.py` | CRUD, join by code, member listing | 120 |
| `inst/internal/repositories/tasks.py` | Tasks, submissions, pages, queue reads | 140 |
| `inst/internal/services/teacher_approval.py` | Apply, decide (audited, grants the `teacher` role scoped to the user via `auth.grant_role`) | 100 |
| `inst/internal/services/batches.py` | Create, join (consent gate), leave, rotate code, remove member | 150 |
| `inst/internal/services/tasks.py` | Create task (CQ-only validation), list for member | 110 |
| `inst/internal/services/submissions.py` | Start, confirm page, submit, student view with label | 160 |
| `inst/internal/services/access.py` | Batch-scoped access rules (teacher of the batch; student owner; staff break-glass audited) | 90 |
| `inst/internal/services/release.py` | Release marks; notifications | 80 |
| `inst/internal/schemas/*.py` | Batches, tasks, submissions (3 files) | 3 × 90 |
| `inst/internal/routes/teacher.py`, `student.py`, `admin.py` | Thin routes | 120, 100, 60 |

**AI marking (AI-07 to AI-07d)**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `ai/internal/models/marking.py` | `MarkingJob`, `Grading`, `GradingPart`, `AccuracyReport` | 120 |
| `ai/internal/repositories/marking.py` | Jobs, gradings and parts insert, final flip, queue reads | 150 |
| `ai/internal/marking/job.py` | `ai.mark_submission` orchestration: runs, triage, failure path | 160 |
| `ai/internal/marking/transcribe.py` | Transcript route (vision model, "do not correct") and digit extraction | 120 |
| `ai/internal/marking/score_parts.py` | Rubric scoring call per run; structured output schema; validation (marks bounds, evidence substring) | 170 |
| `ai/internal/marking/triage.py` | Disagreement, confidence, flags, boundary → priority and reasons | 90 |
| `ai/internal/marking/injection_guard.py` | Student text as data; instruction-like detection (shares patterns with the tutor `injection.py`) | 70 |
| `ai/internal/services/teacher_marks.py` | Final teacher grading, re-mark, outbox | 130 |
| `ai/internal/services/accuracy.py` | Publish report, release flag per subject, invalidation on prompt or model change | 110 |
| `ai/internal/evals/marking/metrics.py` | QWK, exact, within-one, MAE, bias (SD), per part and total | 140 |
| `ai/internal/evals/marking/bootstrap.py` | Cluster bootstrap intervals by student and question | 100 |
| `ai/internal/evals/marking/runner.py` | Run the double-marked set; write `accuracy_reports` (draft) | 130 |
| `ai/internal/routes/marking.py` | Teacher queue and marks; public accuracy; admin publish | 130 |
| `ai/internal/schemas/marking.py` | Queue item, submission detail, marks request, accuracy report | 140 |

**PAY**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `pay/contracts/provider.py` | `PaymentProvider` protocol and DTOs (`ProviderStatus`, `ProviderEvent`, `SettlementRow`) | 100 |
| `pay/internal/providers/bkash/client.py` | Token, create, execute, query, refund (HTTPX; timeouts 10 s; no retry on execute) | 170 |
| `pay/internal/providers/bkash/sns.py` | SNS signature verification, subscription confirm, message parse | 130 |
| `pay/internal/providers/aggregator.py` | SSLCommerz or aamarPay init, IPN hash, validation, refund | 170 |
| `pay/internal/providers/google_play.py` | Purchase verification, acknowledge, RTDN JWT verify | 160 |
| `pay/internal/providers/fake.py` | Deterministic fake with scripted states (success, timeout, duplicate) | 110 |
| `pay/internal/providers/registry.py` | Provider lookup by name | 40 |
| `pay/internal/models/orders.py` | `Order`, `Payment`, `ProviderEvent`, `StorePurchase` | 140 |
| `pay/internal/models/refunds.py` | `Refund`, `CreditNote` | 60 |
| `pay/internal/models/promo.py` | `Coupon`, `CouponRedemption`, `ReferralCode`, `ReferralCredit`, `PricePoint` | 110 |
| `pay/internal/models/invoices.py` | `Invoice`, `InvoiceSequence`, `ReconciliationRun`, `ReconciliationException` | 110 |
| `pay/internal/repositories/orders.py` | Order lock, payment state transitions, provider events | 150 |
| `pay/internal/repositories/promo.py` | Coupon conditional update, redemption, referral ledger | 110 |
| `pay/internal/repositories/invoices.py` | Next number, invoice insert, credit note | 90 |
| `pay/internal/repositories/recon.py` | Runs, exceptions, payments by business date | 110 |
| `pay/internal/orders/create.py` | Order creation, price and coupon, provider create | 140 |
| `pay/internal/orders/capture.py` | Verify-then-capture transaction | 170 |
| `pay/internal/orders/state.py` | Order and payment state machines (allowed transitions table) | 90 |
| `pay/internal/orders/sweeper.py` | `pay.sweep_pending` job schedule and expiry | 100 |
| `pay/internal/orders/events.py` | `pay.process_provider_event` job | 110 |
| `pay/internal/orders/store.py` | Play purchase flow into capture; acknowledge job | 120 |
| `pay/internal/refunds/service.py` | Request, provider call, confirmation, entitlement adjustments | 170 |
| `pay/internal/refunds/rules.py` | Partial-refund proration, exam-fee rule, AI credit pro rata (pure) | 100 |
| `pay/internal/recon/job.py` | Daily run per provider; matching | 170 |
| `pay/internal/recon/settlement_upload.py` | Parse uploaded settlement CSV/XLSX (per-provider column maps) | 130 |
| `pay/internal/invoices/render.py` | Jinja to PDF (WeasyPrint) with Bangla fonts; storage | 110 |
| `pay/internal/invoices/receipts.py` | SMS receipt via PLAN | 50 |
| `pay/internal/services/coupons.py` | Validate and admin CRUD | 120 |
| `pay/internal/services/referrals.py` | Code issue; credit on first capture | 80 |
| `pay/internal/services/admin.py` | Order search, manual grant and revoke (`pay.grant(source='admin')`), audited | 140 |
| `pay/internal/schemas/*.py` | Orders, refunds, coupons, recon, admin (4 files) | 4 × 100 |
| `pay/internal/routes/orders.py`, `webhooks.py`, `store.py`, `admin.py`, `me.py` | Thin routes | 100, 120, 60, 140, 70 |

**OPS, AUTH, NFR**

| Path | Responsibility | ≈ lines |
|---|---|---|
| `ops/internal/models/content.py` | `Banner`, `Notice` | 60 |
| `ops/internal/services/content.py` | CRUD, audience evaluation, cache | 140 |
| `ops/internal/services/support.py` | Support config, widget token | 70 |
| `ops/internal/console/user_lookup.py` | Lookup and aggregation through public functions | 150 |
| `ops/internal/routes/content.py`, `support.py`, `console.py` | Routes | 100, 50, 110 |
| `auth/internal/models/data_requests.py` | `DataRequest` (exists from B1; extend if needed) | 40 |
| `auth/internal/services/data_requests.py` | Request, approve, emit `user.deletion_requested`/`user.export_requested`, track `module_status` from completion events; imports no other module | 150 |
| `auth/internal/services/admin_users.py` | Suspend and reinstate (revoke sessions) | 90 |
| `auth/internal/routes/data_requests.py`, `admin_users.py` | Routes | 80, 90 |
| `<module>/internal/events/user_lifecycle.py` (new, every module with user data) | Consumers of `user.deletion_requested` and `user.export_requested`; anonymise or export this module's rows; emit the completion event | 60–100 each |
| `nfr/internal/protection/content_limits.py` | HLL counter check, called from PRAC, EXAM review and search through `nfr.track_content_access(user_id, ids)` | 90 |
| `nfr/internal/protection/crawl_detector.py` | Job: sequential-pattern detection over the access log stream | 130 |
| `nfr/internal/protection/canaries.py` | Canary assignment per cohort; leak lookup | 90 |
| `scripts/restore_drill.py` | Automated restore drill (AWS SDK), timed, with a report | 160 |
| `ops/slo/journeys.yaml` + alert rules | SLOs and burn-rate alerts as code | data |

### C.4 Domain rules and validation

**Join code**
- 8 characters from `[0-9A-HJKMNP-TV-Z]`.
- 5 failed attempts per user per 10 min gives 429.
- An expired code gives 410.

**Tasks**
- Items must be `type='cq'` published versions with ≥ 1 rubric point per subpart (else 422 `rubric_missing`).
- `due_at > now`.

**Pages**
- 1–10 per submission.
- JPEG or PNG ≤ 1.5 MB.
- Client quality JSON `{blur_score, rotation_deg, crop_ok}`. The server refuses `crop_ok=false` or `blur_score` below the threshold with 422 `retake_required`.

**Teacher marks**
- Each part's marks are in `[0, subpart.marks]` with a 0.5 step.
- The total is computed, never sent.
- Marking another batch's submission gives 404 (never reveals existence).

**Orders**
- `product.status='active'`.
- One pending order per user per product (409 `order_pending` returns the existing one).
- `payable_poisha ≥ 0`. A zero payable (100% coupon) captures immediately with provider `free` (the only value the `orders.provider` CHECK allows for it).

**Refunds**
- `amount_poisha ≤ captured − refunded`.
- A reason is required (10–500 characters).
- An exam fee after `starts_at` gives 422 `refund_not_allowed`.

**Coupons**
- `valid_from ≤ now ≤ valid_to`.
- Product in scope.
- Per user once (PK).

**Banners**
- `starts_at < ends_at`.
- Audience keys from an allow-list.

### C.5 Caching

| Key | Use |
|---|---|
| `crawl:{user}:{hour}` | HLL, NFR-06a |
| Banners per audience key | 60 s (proposed: `ops:banners:{audience_hash}`) |
| bKash token | Proposed: `pay:bkash:token`, TTL = expiry − 60 s |
| Quota `marking_per_month` | `quota:{user}:marking:{month}` |

### C.6 Error handling

| Code | Status |
|---|---|
| `consent_required` | 403 |
| `rubric_missing` | 422 |
| `retake_required` | 422 |
| `order_pending` | 409 |
| `payment_unverified` | 409, from the callback while the provider status is pending; client keeps polling |
| `refund_not_allowed` | 422 |
| `coupon_invalid` | 422, with reason `expired`, `exhausted`, `not_applicable` or `already_used` |
| `content_rate_limited` | 429 |
| Webhook bad signature | 401 (logged, no processing) |
| Webhook duplicate | 200 |

Provider errors map to `unavailable` (503) for users. Payments are never marked failed on a timeout; they stay `execute_unknown` until a query resolves them.

### C.7 Security

- Webhook endpoints verify signatures before parsing the body into domain objects.
- Raw payloads are stored in `provider_events.payload` with PII fields redacted.
- Payment provider secrets live in the secret store.
- Amounts are always taken from the provider query, never from the client.
- Teacher access is batch-scoped (`inst.access`).
- Staff break-glass access to submissions requires a reason and is audited (v2 §4.10 "operations access is audited").
- Submission page URLs are presigned for 5 min.
- Handwriting pages are never sent to a provider that trains on data (an adapter-level assertion on provider config).
- Data export bundles are encrypted at rest, with a URL valid for 7 days.

### C.8 Workers and job kinds

`ai.mark_submission`, `ai.mark_timeout_sweep` (5 min), `inst.release_notify`, `pay.process_provider_event`, `pay.sweep_pending` (scheduled per order), `pay.expire_orders` (hourly), `pay.acknowledge_play` (hourly), `pay.reconcile_daily` (03:00 Dhaka), `pay.recon_exception_alert` (hourly), `pay.render_invoice`, `pay.send_receipt`, `auth.data_request_due_alert` (daily), `auth.execute_data_request`, `nfr.crawl_detect` (10 min), `ops.restore_drill` (manual or quarterly).

### C.9 Observability

**Metrics:**
- `app_pay_orders_total{provider,status}`
- `app_pay_capture_latency_seconds`
- `app_pay_recon_exceptions_open`
- `app_ai_marking_jobs_total{status}`
- `app_ai_marking_disagreement_ratio`
- `app_inst_review_queue_age_seconds`
- `app_nfr_content_rate_limited_total`

**Dashboards:** "Payments", "Marking queue", "SLO overview".

**Alerts:**
- recon exception older than 48 h;
- capture failures > 2% over 15 min;
- marking queue age p95 > 72 h;
- data request at 25 days;
- each SLO burn rate.

### C.10 Configuration

- Settings from step C1.
- `runtime_config`: `payments_enabled`, `android_in_app_purchase`, `support_links`, `helpdesk_widget`, `content_distinct_per_hour` (600), `marking_practice_estimate_enabled` (false).

---

## D. API contracts

### D.1 Teacher-checked marking

| Method / route | Request | Response | Auth / authorization | Errors | RL / Idem |
|---|---|---|---|---|---|
| `POST /v1/teacher/applications` | `{subject_node_ids[], institution_id?, evidence (≤1000)}` | 201 `{id, status: "pending"}` | User | 409 already pending or approved | T-write / R |
| `GET /v1/admin/teacher-applications` | `?status` | `Page<Application>` | Staff:teacher.approve | – | T-admin / – |
| `POST /v1/admin/teacher-applications/{id}:decide` | `{decision: approve|reject, note}` | 200 | Staff:teacher.approve; audited | 409 | T-admin / R |
| `POST /v1/teacher/batches` | `{name, subject_node_id}` | 201 `{id, join_code, join_code_expires_at}` | Role:teacher | 422 | T-write / R |
| `GET /v1/teacher/batches` | – | `Page<Batch>` | Role:teacher (own) | – | T-read / – |
| `POST /v1/teacher/batches/{id}/join-code:rotate` | `{expires_in_days ≤ 90}` | `{join_code, join_code_expires_at}` | Teacher of the batch | 404 | T-write / – |
| `GET /v1/teacher/batches/{id}/members` | `?cursor` | `Page<Member{user_id, first_name, joined_at, status}>` | Teacher of the batch | 404 | T-read / – |
| `DELETE /v1/teacher/batches/{id}/members/{user_id}` | – | 204 | Teacher of the batch | 404 | T-write / – |
| `POST /v1/batches:join` | `{join_code}` | 200 `{batch_id, name, teacher_first_name}` | User; under-18s need consent | 403 `consent_required`, 404, 410 | T-write / R |
| `POST /v1/batches/{id}:leave` | – | 204 | Member | 404 | T-write / – |
| `POST /v1/teacher/batches/{id}/tasks` | `{title, due_at, items: [question_version_id] (1–10)}` | 201 `Task` | Teacher of the batch | 422 `rubric_missing` | T-write / R |
| `GET /v1/batches/{id}/tasks` | – | `Page<Task{id, title, due_at, items[], my_status?}>` | Member or teacher | 404 | T-read / – |
| `POST /v1/tasks/{task_id}/submissions` | `{question_version_id}` | 201 `{submission_id, upload_purpose: "submission_page"}` | Member | 409 exists (returns it), 410 past due | T-write / R |
| `POST /v1/submissions/{id}/pages` | `{page_no, upload_key, sha256, quality{blur_score, rotation_deg, crop_ok}}` | 200 `{page_no, accepted}` | Owner | 422 `retake_required`, 409 after submit | T-upload / R |
| `POST /v1/submissions/{id}:submit` | `{page_count}` | 202 `{status: "submitted"}` | Owner | 422 pages missing | T-write / R |
| `GET /v1/submissions/{id}` | – | `{status, label: "teacher_checked"|"practice_estimate"|null, released_at, total?, parts?: [{label, marks, max, evidence_quote, missing_points[], rewrite_suggestions, model_answer_html}]}`; parts only after release | Owner | 404 | T-read / – |
| `GET /v1/teacher/review-queue` | `?batch_id&cursor` | `Page<QueueItem{submission_id, student_first_name, task_title, priority, reasons[], submitted_at}>` | Role:teacher (own batches) | – | T-read / – |
| `GET /v1/teacher/submissions/{id}` | – | `{pages: [{page_no, url}], drafts: [{run_no, parts[...]}], rubric: [...], transcript?, flags[]}` | Teacher of the batch | 404 | T-read / – |
| `POST /v1/teacher/submissions/{id}/marks` | `{parts: [{subpart_id, rubric_point_id?, marks, comment?}], overall_comment?}` | 200 `{grading_id, total}` | Teacher of the batch | 422 bounds; 404 | T-write / R |
| `POST /v1/teacher/tasks/{id}:release` | `{submission_ids?: [...] }` (default all checked) | 200 `{released: n}` | Teacher of the batch | 409 unchecked | T-write / R |
| `GET /v1/marking/accuracy` | `?subject_node_id` | `[AccuracyReport{subject, part, model, prompt_version, sample_size, metrics, interval, gate, measured_on}]` | Public | – | T-read / – |
| `POST /v1/admin/marking/accuracy-reports` | `{report_id, publish: true}` | 200 | Staff:ai.publish; audited | 409 gate failed (can publish as `failed` for transparency but never releases drafts) | T-admin / R |

### D.2 Commerce

| Method / route | Request | Response | Auth | Errors | RL / Idem |
|---|---|---|---|---|---|
| `POST /v1/orders` | `{product_id, coupon_code?, provider: "bkash"|"aggregator", return_url}` | 201 `{order_id, payable: Money, provider, redirect_url? , sdk_payload?, expires_at}` | User | 409 `order_pending`, 422 `coupon_invalid`, 503 `kill_switch` (payments disabled) | T-write / R |
| `GET /v1/orders/{id}` | – | `{status, payable: Money, paid_at?, entitlement_id?, invoice_id?}` | Owner | 404 | T-read / – |
| `POST /v1/orders/{id}/callback` | `{provider_payment_id, status_hint}` | 200 `{status}`; triggers execute (bKash) or validation (aggregator) then capture. `202 payment_unverified` while pending. | Owner | 409, 410 expired | T-write / R |
| `POST /v1/coupons:validate` | `{code, product_id}` | `{valid, discount: Money, payable: Money, reason?}` | User | – | T-write / – |
| `GET /v1/me/referral` | – | `{code, share_url, credits: Money, history[]}` | User | – | T-read / – |
| `GET /v1/me/invoices` | `?cursor` | `Page<Invoice{id, invoice_no, amount: Money, issued_at}>` | User | – | T-read / – |
| `GET /v1/me/invoices/{id}/pdf` | – | 302 to a signed URL | Owner | 404 | T-read / – |
| `POST /v1/store/purchases/google` | `{product_id, purchase_token, order_id_play}` | 200 `{entitlement_id, status}` | User | 409 token used by another user, 422 invalid | T-write / R |
| `POST /v1/webhooks/bkash` | SNS message (JSON) | 200 | Signed (SNS) | 401 bad signature | T-webhook / dedupe |
| `POST /v1/webhooks/aggregator` | Provider IPN form | 200 | Signed (hash) | 401 | T-webhook / dedupe |
| `POST /v1/webhooks/google-play` | Pub/Sub push (JWT) | 200 | Signed | 401 | T-webhook / dedupe |
| `GET /v1/admin/orders` | `?user_id&status&provider&from&to&cursor` | `Page<OrderAdmin>` | Staff:pay.read | – | T-admin / – |
| `POST /v1/admin/entitlements` | `{user_id, product_id, starts_at?, ends_at?, reason}` | 201 `Entitlement` | Staff:pay.grant; audited | 422 | T-admin / R |
| `POST /v1/admin/entitlements/{id}:revoke` | `{mode: revoke|shorten, ends_at?, reason}` | 200 | Staff:pay.grant; audited | 409 | T-admin / R |
| `POST /v1/admin/payments/{id}/refunds` | `{amount_poisha, reason}` | 202 `{refund_id, status}` | Staff:pay.refund; audited | 422 `refund_not_allowed`/amount | T-admin / R |
| `GET /v1/admin/reconciliation/runs` | `?provider&from&to` | `Page<Run{…, exceptions_open}>` | Staff:pay.finance | – | T-admin / – |
| `POST /v1/admin/reconciliation/uploads` | `{provider, business_date, upload_key}` | 202 `{run_id}` | Staff:pay.finance; audited | 409 run exists | T-admin / R |
| `POST /v1/admin/reconciliation/exceptions/{id}:resolve` | `{resolution, note}` | 200 | Staff:pay.finance; audited | 409 | T-admin / R |
| `POST/PATCH /v1/admin/coupons[/{id}]` | `{code, kind, value, max_redemptions, valid_from, valid_to, product_scope}` | 201/200 | Staff:pay.catalogue; audited | 409 code exists | T-admin / R |

### D.3 Operations, identity and admin

| Method / route | Request | Response | Auth | Errors | RL / Idem |
|---|---|---|---|---|---|
| `GET /v1/banners` | `?placement` | `[Banner{id, title, body, image_url, link, priority}]` (audience-filtered) | User | – | T-read / – |
| `GET /v1/notices` | `?cursor` | `Page<Notice>` | User | – | T-read / – |
| `POST/PATCH /v1/admin/banners[/{id}]`, `/v1/admin/notices[/{id}]` | Banner or notice fields | 201/200 | Staff:ops.content; audited | 422 | T-admin / R |
| `GET /v1/support/config` | – | `{faq_url, call_number, whatsapp_url, widget: {kind, enabled}}` | User | – | T-read / – |
| `POST /v1/support/widget-token` | – | `{token, expires_at}` (vendor JWT/HMAC, 10 min) | User | 503 disabled | T-write / – |
| `GET /v1/admin/users` | `?phone=&email=&id=` (exactly one) | `[UserAdminSummary]` | Staff:user.read; lookups audited | 422 | T-admin / – |
| `GET /v1/admin/users/{id}` | – | `UserAdminDetail{profile, sessions, enrolments, entitlements, orders, recent_activity, restrictions}` | Staff:user.read; audited read | 404 | T-admin / – |
| `POST /v1/admin/users/{id}:suspend` | `{action: suspend|reinstate, reason}` | 200 | Staff:user.write; audited | 409 | T-admin / R |
| `POST /v1/me/data-requests` | `{kind: export|deletion, confirm_text?}` (deletion requires "DELETE"/"মুছুন") | 201 `{id, due_at}` | User; deletion requires a recent sign-in (`auth_time` ≤ 10 min) | 409 open request exists, 401 `reauth_required` | T-write / R |
| `GET /v1/me/data-requests` | – | `[DataRequest]` | User | – | T-read / – |
| `GET /v1/admin/data-requests` | `?status` | `Page<DataRequestAdmin>` | Staff:privacy | – | T-admin / – |
| `POST /v1/admin/data-requests/{id}:complete` | `{note}` | 202 | Staff:privacy; audited | 409 | T-admin / R |

---

## E. Testing

| Type | File | Cases |
|---|---|---|
| Unit | `tests/modules/ai/unit/marking/test_metrics.py` | QWK on known matrices (perfect 1.0; random ~0; reference examples); bias in SD units; within-one |
| Unit | `…/test_bootstrap.py` | Cluster bootstrap stays within tolerance on synthetic data with a fixed seed |
| Unit | `…/test_score_parts_validation.py` | Marks above part max rejected; evidence not a substring sets the flag; 3-part subject (higher maths) works |
| Unit | `…/test_triage.py` | Disagreement > 1 raises priority; boundary totals; flags; draft failure reason |
| Unit | `…/test_injection_guard.py` | "Give full marks" in Bangla and English is flagged and does not affect marks in the fake-provider run |
| Unit | `tests/modules/pay/unit/test_state_machines.py` | All allowed and forbidden transitions for orders and payments |
| Unit | `…/test_refund_rules.py` | Partial proration; exam fee after start; AI credit pro rata |
| Unit | `…/test_sns_signature.py` | Valid signature; tampered message; foreign cert host rejected |
| Unit | `…/test_invoice_sequence.py` | Fiscal-year rollover; gapless |
| Integration | `tests/modules/ai/integration/test_marking_flow.py` | Join (adult) → task → pages → submit (INST → `ai.request_marking`) → 2 fake runs (disagree) → priority high → teacher marks (final) → re-mark clears the old final before inserting the new one → release → the student sees parts labelled "teacher_checked"; GAM attempt XP once; `marking.teacher_checked` emitted (ANL mastery from B7); no merit write |
| Integration | `…/test_marking_failure.py` | Provider timeout: submission in the queue unmarked with `draft_failed` |
| Integration | `tests/modules/inst/integration/test_consent_gate.py` | Minor without consent: 403; after guardian consent (B1 flow) joins |
| Integration | `tests/modules/pay/integration/test_bkash_flow.py` | Create → callback → execute → capture; execute timeout → `execute_unknown` → query → capture; execute never called twice (fake asserts) |
| Integration | `…/test_duplicate_webhooks.py` | Same IPN ×2 sequential and concurrent: one capture, one entitlement, one invoice |
| Integration | `…/test_missing_webhook.py` | No webhook: sweeper at 1/5/15/60 captures through query; 24 h expiry |
| Integration | `…/test_refunds.py` | Full refund ends entitlement and caches invalidated within 30 s; partial shortens; overlapping entitlement keeps access (union); credit note created |
| Integration | `…/test_reconciliation.py` | Paid-not-captured gets auto-captured and notified; captured-not-paid suspends; amount mismatch raises an exception; settlement upload path; 48 h alert |
| Integration | `…/test_google_play.py` | Token verified, captured, acknowledged; reused token by another user gives 409; RTDN refund revokes |
| Integration | `…/test_coupons.py` | Once per user; exhausted; 100% coupon captures with provider `free`; a redemption unique violation inside capture rolls back only the savepoint, so capture commits and an exception is opened |
| Integration | `…/test_duplicate_payment.py` | Second successful payment on a paid order: `duplicate_captured`, exception opened, auto-refund job completes; a crash after the `execute_requested` commit never leads to a second Execute |
| Integration | `tests/modules/auth/integration/test_data_requests.py` | Event-driven: `user.deletion_requested` reaches every registered module consumer, `module_status` reaches all done, and the bundle contains each module's section. Deletion anonymises (phone/email hashes replaced, external identities removed, threads purged, pages deleted) and keeps the pseudonymous ledger. Idempotent redelivery. `check_boundaries.py` confirms AUTH imports no other module. |
| Integration | `tests/modules/nfr/integration/test_content_protection.py` | 601st distinct question in an hour gives 429 and a security event; sequential crawl flagged; canary lookup |
| API | `tests/modules/{inst,ai,pay,ops,auth}/api/test_*.py` | Every endpoint in §D: success, validation errors, error codes |
| Authorization | `tests/modules/inst/api/test_batch_isolation.py` | **Batch as tenant:** teacher A cannot list, read or mark batch B's submissions (404); student cannot read another student's submission; staff break-glass requires a reason and is audited; a removed member loses access to new tasks |
| Authorization | `tests/modules/pay/api/test_authz.py` | Admin refunds need `pay.refund`; order of another user gives 404; webhook without signature gives 401 |
| DB | `tests/modules/ai/db/test_grading_constraints.py` | Only one final grading per submission; `is_final` only for teacher |
| DB | `tests/modules/pay/db/test_constraints.py` | Unique provider txn; payable check; coupon redeemed ≤ max |
| Concurrency | `tests/modules/pay/concurrency/test_capture_race.py` | Webhook + callback + sweeper simultaneously: exactly one capture (R9) |
| Concurrency | `…/test_coupon_race.py` | 50 users redeem a 10-use coupon at once: exactly 10 redemptions (R11) |
| Concurrency | `…/test_invoice_race.py` | 100 concurrent captures: invoice numbers contiguous, no duplicates (R19) |
| Concurrency | `tests/modules/ai/concurrency/test_teacher_double_submit.py` | Two teachers or two tabs marking: one final, the other 409 `version_conflict` |
| Failure | `…/test_provider_outage_pay.py` | bKash down: orders stay pending and the user sees "যাচাই হচ্ছে"; recovery path via the sweeper |
| Regression | `tests/regression/test_p0_gates.py` | v2 §8.2 gate checks that are automatable: duplicate, missing webhook, refund, reconciliation mismatch; cross-user answer id never returns another user's data (B3); cache privacy (B4); exam fault replay summary (B5 artefact present) |
| Eval | `tests/modules/ai/eval/marking/test_smoke.py` (`-m eval`) | 30-answer recorded set: pipeline output schema-valid; metrics computed; gate logic |
| Performance | `tests/load/payments_burst.py` (manual) | 200 orders/min with duplicate webhooks: capture p95 < 2 s; no duplicates |
| Recovery | `scripts/restore_drill.py --dry-run` in CI; full run in staging | Drill report: RTO measured (target 1 h), RPO (5 min) verified by the last-write timestamp |

**Coverage.** 85% overall. **95%** on:
- `pay/internal/orders/*`, `pay/internal/refunds/*`, `pay/internal/recon/job.py`
- `ai/internal/marking/*`, `ai/internal/services/teacher_marks.py`
- `inst/internal/services/access.py`
- `auth/internal/services/data_requests.py`

---

## F. Completion

### F.1 Acceptance criteria

1. The end-to-end marking flow passes. A teacher can only access their own batches (isolation test). The teacher mark is final and drafts are never overwritten.
2. `evalcli marking` produces an `accuracy_reports` row with QWK, bias, intervals and gate for a subject's double-marked set. Publishing makes it visible at `/v1/marking/accuracy`. Drafts are released only for subjects whose gate is `teacher_review` or better. Whether a real subject passes is reported, not assumed (D9).
3. The payment gate cases from v2 §8.2 pass against fakes and, where credentials exist, in the bKash and aggregator sandboxes:
   - duplicate webhook;
   - missing webhook;
   - full and partial refund;
   - reconciliation mismatch.
4. There is no double capture under concurrency (R9), no coupon over-redemption (R11), and invoice numbers are gapless (R19).
5. Every admin write in this build has an `ops.audit_log` row (test enumerates admin routes and asserts audit rows).
6. Data export and deletion complete within the test in one run; anonymisation leaves no plaintext PII (column scan).
7. Content protection returns 429 above the distinct-question limit and logs a security event.
8. SLO and burn-rate alerts are defined for the 4 journeys and fire in a staging test (synthetic failure injection).
9. The restore drill runs in staging with a recorded RTO ≤ 1 h and RPO ≤ 5 min.
10. **The 25,000-candidate exam rehearsal passes** using the B5 harness.
11. The P0 traceability check shows all 93 P0 IDs implemented with tests ([`16`](16_feature_traceability_matrix.md)).

### F.2 Deliverables

- Migrations `b06_01`–`b06_09`.
- The INST minimal module.
- The AI marking pipeline and accuracy tooling.
- The PAY gateways, orders, refunds, reconciliation and invoices.
- OPS console, content and support APIs.
- The data requests workflow.
- Content protection.
- SLOs and alerts as code.
- The restore drill script and report.
- The 25k rehearsal report.
- The pen-test readiness pack (OWASP API mapping, authz matrix, scan reports).
- The `openapi.json` update.
- **The P0 completion report.**

### F.3 Definition of done

[`21_definition_of_done.md`](21_definition_of_done.md), plus the P0 completion checklist:
- all §8.2 gates that the backend can evidence are evidenced;
- external gates (pen test, field device tests) are listed with owners.

### F.4 Manual verification checklist

- [ ] Apply as a teacher; approve as ops; create a batch; join as a 17-year-old test user; confirm consent is required; complete guardian OTP; join.
- [ ] Upload 3 pages, submit, and watch the job produce 2 drafts and triage reasons in the teacher queue.
- [ ] Mark as the teacher, release, and view as the student: labels and parts.
- [ ] Buy a product with bKash sandbox (or fake): approve, redirect, confirm access, receipt PDF and SMS.
- [ ] Send the same IPN twice and confirm one capture.
- [ ] Refund half: confirm the shortened entitlement and the credit note.
- [ ] Upload a settlement file with one mismatch and resolve the exception.
- [ ] Look up a user by phone in the admin console and confirm the audit row.
- [ ] Create a banner for "SSC 2028, district Dhaka" and confirm targeting.
- [ ] Request deletion as a test user, complete it as staff, and confirm anonymisation.

### F.5 Exit criteria before the next build

- P0 completion report approved by the supervisor.
- Open external items have owners: pen test, merchant live tests, D2 and D9 outcomes.
- `live_exam_cap` raised to 50,000 only via an audited config change after the 50k rehearsal (outside this build).
- No open high or critical security findings.

---

## Proposed additions (accepted)

All items below were reviewed during integration and **accepted**. Redis keys are in [`01`](01_database_design.md) §3.17, columns and constraint values in 01 §3/§4, and error codes in [`14`](14_api_contracts.md) §1.5. Cross-module functions listed here are part of the owning module's public API (`__init__.py`).

| Kind | Item | Reason |
|---|---|---|
| Redis key | `ops:banners:{audience_hash}`, JSON, 60 s, rebuilt from `ops.banners` | Banner cache |
| Redis key | `pay:bkash:token`, string, provider TTL − 60 s, refetched | bKash token grant cache |
| Column | `institution.batches.join_failures` is **not** added; join brute-force uses the rate limiter `rl:join:{user}` (the existing family) | Clarification only |
| Columns | `commerce.payments.status` adds `execute_unknown`; `commerce.orders.status` adds `partially_refunded` (in 01 already) | State machines |
| Error codes | `consent_required`, `rubric_missing`, `retake_required`, `order_pending`, `payment_unverified`, `refund_not_allowed`, `coupon_invalid`, `content_rate_limited` | Add to 14 §1.5 |
| Function and event contracts (revised after review R-03/R-28) | Events `user.deletion_requested`, `user.deletion_completed`, `user.export_requested`, `user.export_part_ready`, `marking.teacher_checked`. Public functions: `ai.request_marking()`, `ai.get_drafts()`, `ai.record_teacher_marks()`, `qb.get_cq_rubric()`, `auth.has_guardian_consent()`, `auth.grant_role()`. No `export_user`/`anonymise_user` functions; no `anl.record_teacher_mark` in B6 | Cross-module contracts used here |
| Quota feature | `marking_per_month` in `commerce.quota_policies` seed | Marking needs its own quota (v2 §4.10 cost) |

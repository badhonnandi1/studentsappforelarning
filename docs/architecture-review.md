# Pre-build architecture and module complexity review

**Date:** 2026-11-26 · **Reviews:** [`system-design.md`](system-design.md) · **Requirements:** [`features.md`](../features.md)

Sources:

- `features.md`: requirements and priorities.
- `docs/system-design.md`: the proposal under review, cited as §n.
- `initial_plan.md`: identical to the proposal apart from the header and the last section heading. Historical context only.

Labels used throughout:

- **[Doc]**: stated in `features.md` or the design.
- **[Est]**: my estimate.
- **[Needs evidence]**: a claim nobody has checked yet.

**Nothing in the design has been measured.** Every test in it is a verification plan, not a result.

---

## 1. Verdict: **Start with conditions**

**The three strongest reasons**

1. **The foundations are sound, cheap to start and low-regret.** These are: a modular monolith on PostgreSQL; attempts pinned to a question version (QB-06); device-generated idempotency keys; an outbox feeding the event log (NFR-09); an append-only XP ledger; `tenant_id` on every content row (§2, §3). They are standard patterns. None of them depends on an open decision.
2. **Three correctness gaps must be fixed on paper before the affected code is written.**
   - The live-exam finalisation window contradicts the late-answer window (§6.2 vs §6.3).
   - The tutor's shared cache can store an answer generated with one student's personal context (§4.2 vs §4.6).
   - The practice answer id is a global primary key, so a replayed id can return another user's row (§3.5).

   Each is a one-day design fix. Each becomes an expensive rework if it is coded first.
3. **The plan does not yet add up for a week-24 national launch.**
   - The specialist roles are overbooked: backend, AI/ML, platform and QA (§4 of this review).
   - Content review needs 33–40 full-time reviewers if the 150,000-question bank is unverified **[Est]**, and the plan has none.
   - Four external decisions (D1, D2, D4, merchant onboarding) gate parts of P0.

**Can start this week:** platform skeleton; AUTH; TAX; QB data model; PRAC session and answer API; GAM ledger and streak engine; AI gateway skeleton with quotas and exam lockout; tutor explanations grounded on the verified question bank; the Android device spike; the OCR and model shortlist evaluation; inventory of the existing question bank.

**Blocked**

| Work | Blocked by |
|---|---|
| Textbook ingestion and page citations at scale | D1, rights to index NCTB textbooks |
| Choosing a model for each tutor route; photo-solve launch scope | D3 |
| Live payment integration | bKash and aggregator merchant accounts, and D2 (Play policy) |
| Final minors' consent flow; collecting handwriting photos from minors for evaluation | D4 |
| Build order for exam-scale work (20,000 vs 200,000 at launch) | D5 |

**Milestone credibility [Est]**

| Milestone | Credible? | Condition |
|---|---|---|
| Week 6: learning session on staging | **Yes, with scope control** | One SSC Physics chapter, verified by hand. Tutor cites the verified explanation and question id; a textbook page is cited only if D1 allows. Android may be a debug build. |
| Week 16: pilot | **Yes, if the pilot is free** | No payments in the pilot. Live exams capped at 5,000. Photo solve labelled beta. About 15,000 verified questions for one track. |
| Week 24: P0 launch | **Not as written** | Feasible in weeks 24–28 only with about 3 added people and the simplifications in §6 of this review. Otherwise weeks 28–34. |
| First 200,000-candidate national exam | **Not at week 24** | Needs staged events at 20,000, then 50,000, then 200,000, each after a rehearsal. Realistic 6–10 weeks after launch. |

**Two separate decisions:**

- **Readiness to start development: yes.**
- **Readiness for a national launch: no.** That needs passed gates (§8.2) that have not been measured yet.

---

## 2. Module-by-module assessment

**Scale:**

- **1:** an isolated, well-understood workflow.
- **3:** several components or state transitions, using known patterns.
- **5:** demanding correctness, scale or specialist-quality requirements across components.

**Effort** is P0 person-weeks **[Est]**: backend, client and automated tests for that module. Integration and hardening (about 20 person-weeks) is counted once, in §4. **Confidence** refers to the effort range.

| Module | P0 complexity /5 | Full P0–P2 /5 | P0 effort (pw) | Confidence | Main complexity driver (hardest concrete requirement) | Critical dependency | Readiness to start |
|---|---:|---:|---|---|---|---|---|
| AUTH | 3 | 4 | 4–7 | Medium | Single active session during live exams (AUTH-02, §3.4): takeover via epoch and an exam token checked without the database. Also OTP abuse controls (NFR-06) and guardian OTP consent pulled into P0 (§7.5). | SMS vendor contract; D4 for consent rules | Start now. Consent screens after D4. |
| TAX | 2 | 3 | 2–4 | High | One question mapped to several yearly syllabus versions (TAX-03, §3.1). Building the trees for every admission and job track (TAX-02a, TAX-02b) is content work, not code. | Curriculum experts to author the trees | Start now |
| QB | 4 | 4 | 10–16 | Low | Ten question types with rich content (QB-01 to QB-02). Immutable bilingual versions (QB-05, QB-06). Bangla and maths OCR import (QB-07a). Near-duplicate detection with maths normalisation (QB-08, §7.1). | Choice of OCR engine; a sample of the real bank | Data model: start now. OCR import: after the week-2 spike. |
| CMS | 3 | 3 | 8–12 | Medium | Blind two-person key verification, plus correction → rescoring → notification (CMS-02, CMS-04a, §7.1 steps 5 and 9–11). The WYSIWYG editor with LaTeX and Bangla preview (CMS-01) carries the effort risk. | QB versions; content team process | Start now. Build the editor on an existing framework. |
| PRAC | 3 | 4 | 6–9 | Medium | Idempotent offline-safe answers and the Mistake Notebook rule "cleared after 2 correct in a row", computed from ordered attempts (PRAC-05, §1.2). P1 adaptive practice and spaced repetition raise the full score. | QB published content; event outbox | Start now. Core of week 6. |
| EXAM | 5 | 5 | 14–22 | Low | 200,000 candidates with a synchronised start, durable acknowledgement, a server timer, recovery and merit lists (NFR-01, EXAM-04a to EXAM-06, §6.2). Open design gaps remain (§3.1 of this review). | Exam design fixes; platform load harness; D5 | **Start with conditions.** Blueprint and attempt model now; ingest only after the §6.2/§6.3 fix. |
| ANL | 2 | 4 | 3–5 | Medium | Readiness score per track (ANL-01) uses a proposed rule (§1.4). The rest are projections. P1 item statistics and forecasts raise the full score. | PRAC and EXAM events | Start by week 4 |
| AI | 5 | 5 | 14–24 | Low | Bangla and Banglish answers grounded with verified page citations (AI-01, AI-02, AI-02a). Handwritten Bangla maths photo solve (AI-03). Launch gates on quality and cost (AI-15a, §4.8). | D1 (textbook rights); D3 (model quality); teacher time for evaluation | **Start with conditions.** Gateway, evaluation harness and bank-grounded explanations now. Textbook retrieval after D1. |
| GAM | 3 | 4 | 5–8 | Medium | Streaks on Asia/Dhaka dates with offline "effective time", freezes and late syncs; a leaderboard matrix of period × audience × track (GAM-02, GAM-03, §5.3–§5.5). Several rules are undecided (§3.3 of this review). | Product decisions on the rules | Start now. The ledger is independent of the rules. |
| PLAN | 2 | 3 | 2–4 | High | Notification inbox plus push to 200,000 recipients in cohorts, with quiet hours for minors (PLAN-02, §7.4). | FCM; SMS vendor | Start by week 4 |
| COM | 2 | 4 | 1–2 | Medium | A Bangla and Banglish profanity filter with mixed spellings (COM-05). Minor-safety rules (COM-04, P2) raise the full score. | None | Start late (week 8 or after) |
| PAR | N/A | 3 | N/A (≈0.5 in other modules) | Medium | P1: parent controls enforced across devices, such as the tutor mode lock and daily time cap (PAR-03). **Launch hooks:** the guardian-consent record in AUTH (NFR-07) becomes the parent link; `beneficiary_user_id` on entitlements (PAR-04); a mode field on tutor threads (AI-06). | AUTH consent model | P1. Add hooks in P0. |
| INST | N/A | 5 | N/A (≈1–2 in QB, EXAM and NFR) | Low | P1: private question isolation across tables, search, embeddings and caches (INST-03, §7.3); phone OMR scanning (INST-05); Bangla print typesetting (INST-06). **Launch hooks:** `tenant_id` on content and exams; cross-tenant read tests; audience-restricted exams (EXAM-02); an institution reference list. | Tenant model in QB, EXAM, search | P1. Add the hooks in P0; retrofitting them later is expensive. |
| PAY | 4 | 4 | 7–11 | Medium | Verify-then-capture with duplicate and missing webhooks, refunds and daily reconciliation, across bKash, an aggregator and Play Billing (PAY-03, PAY-05, §7.2). Entitlements and free quotas (PAY-02). | Merchant onboarding; D2; bKash API details **[Needs evidence]** | Entitlement engine: now. Gateways: blocked by accounts and D2. |
| OFF | 4 | 5 | 12–18 | Low | Android 8 on 2 GB RAM, APK under about 30 MB, plus exam recovery from local storage (OFF-01, EXAM-05, §0.3, §6.6). P1 offline packs with conflicts and P2 iOS raise the full score. | Week-2 device spike | **Start now.** The spike is the first task. |
| OPS | 3 | 3 | 5–8 | Medium | Live-exam control room: extend time and invalidate a question while 200,000 are sitting (OPS-01a, §6.2 step 12). The rest is CRUD and audit (OPS-01 to OPS-04). | EXAM, PAY interfaces | Start by week 8. Buy the helpdesk. |
| NFR | 5 | 5 | 14–22 | Low | 99.9% availability with zero acknowledged-answer loss at 200,000 (NFR-01 to NFR-03, §6.3–§6.4). Bangla, Banglish and maths search (NFR-04, §7.1). The event pipeline (NFR-09). Content protection (NFR-06a). | Platform engineer (one person); load-test tooling | Start now |

**P0 total: 108–174 person-weeks before integration [Est].**

**Five hardest modules, in rank order**

1. EXAM
2. AI
3. NFR
4. OFF
5. QB (PAY is close behind)

**Which of them control the delivery date**

- **AI.** External decisions (D1, D3), one AI engineer and teacher-graded evaluation sets.
- **EXAM with NFR.** One platform engineer and an unmeasured load path. 200,000 cannot be proven until about week 20 under the current plan.
- **QB, through content throughput.** The code is manageable; verifying the bank is not (§4 of this review).

OFF controls the date only if the week-2 spike fails. A Kotlin exam screen would add about 3–4 weeks **[Est]**.

---

## 3. Scenario challenges

### 3.1 Live exam: an answer acknowledged five minutes after the end

| | Finding |
|---|---|
| **Design guarantees [Doc]** | The acknowledgement is sent only after SQS stores the message (§6.2 step 7). Consumers upsert, and the highest sequence wins (§3.5). |
| **Contradiction [Doc]** | §6.2 finalises and scores every attempt at end + 60 s. §6.3 accepts unsent answers until end + 10 min. An answer acknowledged at end + 5 min arrives after its attempt was scored. The design does not say whether it is rejected, which breaks the §6.3 promise, or whether it triggers a rescore. |
| **When it is scored** | Undefined today. |
| **When the merit list can publish** | §6.4 sets publication at end + 10 min or later for large exams. That is the same moment the late window closes, with no time to drain the queue or reconcile. |
| **Does matching the highest sequence prove every earlier answer was saved?** | **No.** (a) If two batches are in flight and the earlier one (seq 38–40) is lost while the later one (41–43) is acknowledged, the client's `acked_seq` becomes 43. It then never resends 38–40, because §6.2 step 8 resends only answers above `acked_seq`. (b) The "highest acknowledged sequence" lives in ingest's Redis, which is not durable. (c) The upsert keeps only the latest answer per question, so gaps cannot be detected afterwards. |
| **Smallest design change** | (1) One batch in flight per client; each batch carries every unacknowledged answer; the acknowledgement covers that contiguous range. (2) Store batches append-only, keyed by (attempt, seq), next to the latest-answer table. (3) Two-phase close: provisional score at end + 60 s for monitoring only; a hard close at end + 10 min; then the queue and dead-letter queue must both be empty; then the contiguity check (seq 1..N present for every attempt); then final scoring. Merit publishes at end + 15 min or later. (4) Reject or flag answers whose client effective time is after `ends_at`. |
| **Smallest test** | A fault-injection test with 20,000 simulated clients: drop 1% of batches at random after send, kill a consumer, deliver 2% of answers between end + 1 and end + 9 min. **Pass:** every acknowledged answer is scored, the contiguity check finds every gap, and the merit list is identical across three replays. |

**Two load findings the design misses**

- **Synchronised autosave waves.** All clients start at T0 with 15-second timers, so their flushes line up. About 84,000 requests would land in 1–2 seconds every 15 seconds: 3–6 times the 13,333 per second planned in §6.1 **[Est]**. The fix is a random phase per client.
- **Result-page rush.** Students watch the countdown rather than wait for the cohorted push (§6.4). Up to 200,000 reads can arrive within about 20 s, roughly 10,000 per second **[Est]**. The fix is to serve each student's result as a precomputed object from Redis or a signed CDN object, with no database query on that path.

### 3.2 AI tutor

**Banglish question "option kha bhul keno?" (§4.2)**

- **Guaranteed [Doc]:**
  - Intent comes from the screen's context, the `answer_id`.
  - The verified key is part of the context.
  - Citations are checked against chunk metadata.
  - A disagreement with the key forces a retry, then "not sure".
- **Gap:** the shared canonical cache is keyed by content only. On a cache miss, the answer is generated with "up to three recent mistakes" of that student. If that answer is stored, the next student sees content personalised for someone else.
- **Fix:** generate canonical answers with no personal context. Add any personal note in a separate, uncached step, or drop it at P0.
- **Simplification:** drop the transliteration step. The question-screen buttons (AI-04) carry the intent, and current models read Banglish directly. Keep Banglish folding only for search.

**Handwritten Bangla maths photo (§4.3)**

- **Guaranteed [Doc]:** the recognised problem is shown and confirmed before solving; a verified bank match is used first; the final answer is checked with a computer-algebra tool; similar questions are filtered by permission.
- **Ambiguous:**
  - "Diagram description" quality is untested. AI-03 lists diagrams.
  - The computer-algebra check covers numeric and symbolic answers only, not proofs or geometry.
  - The second OCR read doubles OCR cost for unproven benefit.

**Textbook rights (D1).** Page citations depend on licence to index and quote NCTB books. Until D1 is resolved, the tutor can cite only verified explanations and question ids. That meets AI-02a partially: book and page would be missing.

**Teacher-review effort [Est]**

| Item | Calculation | Result |
|---|---|---|
| Building the evaluation sets | About 3,200 items (1,500 tutor, 400 maths, 500 handwriting, 300 safety, 500 search) × 8 min | 427 h, about 14 teacher-weeks |
| Grading one full run | — | About 120 h, 4 teacher-weeks |
| Six runs graded fully by humans | 6 × 4 | 24 teacher-weeks |
| Six runs with a model grader calibrated against a 20% human sample | — | About 8 teacher-weeks |
| **Total before launch** | | **About 22–38 teacher-weeks** |

The plan does not staff this.

**Collecting handwriting photos.** The 500 handwritten photos come from students, most of them minors. That needs consent (D4) and data-handling rules.

**Cost per resolved answer [Doc arithmetic]**

| Item | Value |
|---|---|
| Gate in §4.8 | ৳1.20, which is $0.0098 at ৳122 per dollar |
| Text tutor reply (§8.6) | $0.0027, about ৳0.33 per message |
| Text reply at a 60% resolution rate **[Est]** | About ৳0.55 per resolved answer. Passes. |
| Photo solve (§8.6) | $0.022, about ৳2.68 per solve |
| Photo solve at the same resolution rate | About ৳4.5 per resolved answer. **Fails the gate.** |

- **Fix:** set the cost gate per route, for example text ৳1.20 and photo ৳5, or state the traffic mix the blended gate assumes.
- **Unverified [Needs evidence]:**
  - Reasoning-token use on the strong tier could be 2–5 times the planned 1,500 tokens.
  - The per-user ceiling ($0.15 a day, about ৳550 a month) is not tied to any plan price.

**Buildable while D1 and D3 are open**

- Gateway, quotas and rate limits.
- Exam lockout.
- Moderation.
- Subject threads.
- The canonical explanation cache.
- Bank-grounded "why is X wrong".
- The citation verifier.
- The photo capture and confirm screens.
- Similar-question search.
- Cost tracking.
- The evaluation harness.
- Prompt versioning.

None of these needs a final model choice.

### 3.3 Gamification: the 11:58 pm answer synced twice after midnight, then a key correction

This replays §5.5. The design's results are: 1 attempt, 5 XP, streak 7 with 26 November counted.

| Effect | Guaranteed [Doc] | Ambiguous: needs an explicit product decision |
|---|---|---|
| Attempt count | One. `answer_id` deduplicates. | **Security gap:** `answer_id` is a global primary key (§3.5). A replay of another user's id would return that user's row. Scope it to (user_id, answer_id). |
| XP | 2 for the attempt, +3 after the correction, one ledger row each | Downward corrections keep the XP while mastery and merit go down. Accept this asymmetry explicitly. Does the late answer complete 26 November's daily goal (+10)? Which date does the 300-XP daily cap use? |
| Streak | 26 November counted, because effective time falls inside the 6-hour window | Web: `performance.now()` resets on every page load, so effective time on the PWA mostly falls back to receipt time and the date moves. Freeze refunds add a reversal path that could be removed (§6 of this review). |
| Leaderboard | +3 goes to the period of the correction; closed boards stay closed | Which period gets the original 2 XP: effective date or receipt time? Here both fall in the same week (Saturday to Friday). On Friday 23:58 → Saturday 00:05 they would not. **Recommend:** boards use receipt time, streaks use effective date. |
| Mistake Notebook | The question is removed after the key correction | PRAC-05 says clearing happens "after 2 correct in a row". Removal by correction is a new rule and needs sign-off. |
| Mastery | Recomputed from attempts and score adjustments | None |
| Official exam merit | Separate record; a correction to a live-exam question creates a new merit snapshot with ops approval (§7.1 step 10) | What happens to published ranks, certificates (EXAM-12, P1) and any prizes when the merit list changes. |

**Minors' privacy (NFR-07).** Under-18s are hidden from national boards until a guardian consents (§5.7). Most users are minors, so national boards could be nearly empty at launch. This needs a product decision: show them with first name and institution by default with an opt-out, or keep them hidden until consent.

**Smallest test.** Turn §5.5 and 20 clock edge cases into table-driven unit tests against the reward and streak engine. Cover midnight, the Saturday rollover, month end, reboots, a skewed device clock and the same answer replayed with a different user. This is already release gate §8.2.

### 3.4 Payments and mobile

**Duplicate bKash notification (§7.2)**

- **Guaranteed [Doc]:** the provider event key is unique; the order row is locked; capture, entitlement and outbox commit in one transaction; access is granted only after a server-side status check.
- **Gap [Needs evidence]:** bKash's tokenised checkout, as I understand it, requires the merchant to call an **Execute Payment** API after the redirect before the payment completes. The §7.2 sequence goes straight from redirect to webhook and status query. Confirm against bKash's current merchant documentation. If confirmed, the execute call must be idempotent and the payment state machine must include it.

**Refund**

- **Defined:** entitlement ends; learning history is kept; AI credits are refunded pro rata.
- **Undefined:**
  - Partial refunds.
  - A refund when another active entitlement covers the same content. Access is a union of entitlements, so access should continue; add a test.
  - Whether bKash and the aggregator give settlement reports through an API or only as portal downloads **[Needs evidence]**. If only downloads, reconciliation (PAY-05) becomes a daily manual upload into the job.

**Play policy (D2) [Needs evidence].** Google's 2026 billing changes cover the US, UK and EEA. Bangladesh terms are not announced. If Play Billing is mandatory for digital subscriptions bought inside the app, in-app bKash checkout may not be allowed. That changes PAY-03 scope, margins and the purchase flow (in the app or on the web).

**Proving the mobile targets on a 2 GB Android device.** Nothing has been measured yet.

- **APK size:** Play Console size report and `bundletool get-size total` per device specification. OFF-01 says "APK under about 30 MB"; §6.6 measures the per-architecture Play download. If the app is also shared as a single universal APK outside Play **[Needs evidence for BD usage]**, that file will exceed 30 MB.
- **Memory:** `adb shell dumpsys meminfo` and the Android Studio profiler through a scripted 100-question, 60-minute exam. Pass: under 300 MB PSS, no ANR.
- **Exam recovery:** automated Maestro or Appium flows with `am force-stop`, network loss and a reboot, then a comparison of server-acknowledged answers against the device log.
- **Devices:** buy 3–4 low-end models common in Bangladesh **[Est]**, plus one Android 8.1 device with an outdated System WebView. KaTeX output needs a WebView capable of KaTeX CSS and fonts. That is a client dependency §0.3 does not mention.

### 3.5 P0 requirements narrowed in the design

| Feature ID | Requirement | Design | Material? |
|---|---|---|---|
| NFR-02 | Result in under 5 s after submit; merit may be deferred | For live exams, 5 s applies to the **submission receipt**; results are withheld until publish time (§6.4, §7.5) | **Yes.** NFR-02 defers only the merit list. Options: provisional score without rank in 5 s, or accept the narrowing explicitly. |
| NFR-02 | Question load under 300 ms on 3G | Measured as a local render after the bundle has loaded; session start gets 2.5 s (§6.4) | Yes. Sound engineering, but a reinterpretation; needs sign-off. |
| OFF-01 | APK under about 30 MB | Per-architecture Play download (§6.6) | Medium |
| QB-01a | CQ written answers | Self-marked, kept out of merit (§3.1) | Medium. CQ is central to SSC and HSC. |
| EXAM-02 | Institution and batch exams | Created by ops only (§7.5) | Low |
| EXAM-06 | Institution rank | Based on the institution the student picks in their profile, so anyone can claim one | **Yes.** Rankings can be manipulated. Label as "self-reported" or delay until rosters exist. |
| AI-02, AI-02a | Grounded in NCTB textbooks, with page citations | Conditional on D1 | **Yes**, if D1 fails |
| AI-03 | OCR including diagrams | "Diagram description", untested | Medium |
| AI-15 | Semantic answer cache | Canonical cache plus a narrow free-form cache; §6 of this review proposes deferring the free-form one | Decision needed |
| NFR-03 | 99.9% availability; AI outage must not stop practice | Tutor availability excluded from the 99.9% (§6.4) | Low. Consistent with "AI down ≠ practice down", but state it. |
| NFR-07 | Leaderboard privacy and parental consent | Under-18s hidden from national boards until consent | Product impact (§3.3) |
| NFR-01 | 200,000 concurrent, load-tested | Proposed staging (§10 recommendation 6) | Needs an explicit milestone change (§5 of this review) |

**Other gaps not tied to a single feature ID**

- Bangla SMS uses Unicode at 70 characters per segment, so OTPs and receipts may cost 2 segments. That doubles the SMS lines in §8.6 **[Est]**.
- VAT (Mushak) invoicing for digital services in Bangladesh is not covered by PAY-04 **[Needs evidence]**.
- Questions scanned from commercial guidebooks (QB-07a) raise copyright and provenance risk. The design does not track content source rights.

---

## 4. Does the delivery plan add up?

### 4.1 Capacity by specialty

Assumptions: 24 weeks; 75% of time productive after meetings, onboarding, leave and on-call **[Est]**; 18 person-weeks per person.

| Role | People | Capacity (pw) | P0 demand (pw) [Est] | Load |
|---|---:|---:|---:|---|
| Backend | 3 | 54 | 55–65 | 100–120% |
| AI/ML | 1 | 18 | 18–24 (tutor, OCR for content and photos, embeddings, evaluation harness) | 100–135% |
| Platform/SRE | 1 | 18 | 20–26 (infrastructure, CI, observability, event log, edge, exam ingest infrastructure, load harness for 250,000 clients, backups) | 110–145% |
| Web | 2 | 36 | 22–28 (learner PWA, CMS editor, admin and control room) | 60–80% |
| Android | 2 | 36 | 20–26 (React Native app, exam screen, sync, device lab) | 55–70% |
| QA | 1 | 18 | 18–26 (device lab, exam and payment matrices, release gates) | 100–145%, peaking in weeks 16–24 |
| **Total** | 10 | **180** | **153–195** | |

The totals count integration and hardening (about 20 person-weeks) once. Shared work counted once: OCR (QB and AI), the offline sync library (OFF), event infrastructure (NFR), integration testing (QA).

**The total roughly fits. The specialties do not:**

- Web and Android have about 20–30 person-weeks of slack.
- Backend, AI/ML, platform and QA have none. There is no buffer for rework or pilot support from week 16.

**Recommended staffing changes**

1. Move one client engineer to backend and API work from week 8.
2. Contract an OCR and evaluation engineer.
3. Add a second QA engineer from week 12.
4. Have backend share load-test work with platform.

### 4.2 Critical path

| Path | Sequence | Controlled by |
|---|---|---|
| A. Content and AI | Bank inventory and OCR choice (weeks 1–2) → import pipeline (3–8) → verification of pilot content (to week 14). Evaluation sets (2–8) → evaluation v1 (10) → photo solve (16–20) → tutor gates (22). | Content team throughput, teacher time, D1, D3 |
| B. Exam | Design fixes (1–2) → ingest and exam screen (3–10) → 20,000-candidate test (10) → 50,000 (14) → 250,000 rehearsal (20) → penetration test → launch | Platform engineer |
| C. Payments | Merchant onboarding (external, weeks unknown **[Needs evidence]**) → integration → live tests (by week 20) | bKash and aggregator onboarding; D2 |

**Genuinely parallel from week 1:** TAX/QB/CMS; PRAC/GAM; the AI gateway; AUTH; clients; platform.

**Bottlenecks**

| Bottleneck | Why |
|---|---|
| AI engineer | Needed for both the content OCR and the tutor in weeks 1–10 |
| Platform engineer | Infrastructure and the exam-scale proof both depend on one person |
| QA | Release gates, pilot and device lab all land in weeks 16–24 |
| Content reviewers | Not in the plan at all (§4.3) |

### 4.3 Content preparation, separate from engineering [Est]

Assumed mix: 80% MCQ, 20% CQ or written. Reviewers work 30 productive hours a week.

| Task | MCQ | CQ | Weighted average |
|---|---|---|---|
| OCR correction, tagging and metadata | 5 min | 12 min | 6.4 min |
| Blind second key verification | 2 min | 8 min | 3.2 min |
| **Per question** | | | **9.6 min** |
| Writing an explanation, where missing | | | +7 min |

| Scenario | Effort | Staffing |
|---|---|---|
| All 150,000 questions unverified | 24,000 h, 800 reviewer-weeks | **33 FTE over 24 weeks** |
| Same, with explanations to write | 41,500 h | **58 FTE over 24 weeks** |
| Bank already verified: import check (1 min) plus a 5% re-verification audit | 2,900 h, 97 reviewer-weeks | 4–5 FTE |
| Pilot track only: about 15,000 questions (500 topics × 30), unverified | 2,400 h, 80 reviewer-weeks | 7 FTE over weeks 2–14 |
| Pilot track only, already verified | About 290 h | 1 FTE |

**Recommendation.** Verify only what launch tracks need. Import the rest as unverified and unpublished. Measure the real minutes per question on 200 bank questions in week 1. The verification status of the existing bank is the largest unknown in the schedule.

### 4.4 Load and queue drain, recalculated

| Item | §6.1 says | Recalculation |
|---|---|---|
| Autosave ceiling | 13,333 per second, spread evenly | Phase-locked waves of about 84,000 within 1–2 s every 15 s without jitter. Fix: random phase per client. |
| Expected autosave rate | 5,600 per second | 200,000 × (1 − e^(−0.0361 × 15)) ÷ 15 = 5,576. Correct. |
| Consumer throughput and drain | 24,000 messages per second; 17 s worst case | A wave of 84,000 drains in about 3.5 s. The consumer side is fine; **ingest and the load balancer are the constraint**. |
| Ingest | 1,500 requests per second per instance in Python | **[Needs evidence]** If it measures 500, 60 instances are needed. Cost stays small, but pre-scaling and load-balancer pre-warming become critical. |
| Postgres writes | Not stated | About 8,000 row upserts per second sustained, about 19,000 at the ceiling **[Est]**. Needs a measured instance size. |
| SQS | "SQS" | Must be a **standard** queue. FIFO queues have per-queue throughput quotas **[Needs evidence: current figures]**. |
| Result publication | 700 per second through cohorted push | Up to about 10,000 reads per second, because students watch the countdown. Serve precomputed results. |
| Lobby sign-ins | Not stated | If 5% of candidates need an OTP in the 15-minute lobby, that is 10,000 SMS. Bangladeshi gateway throughput is **[Needs evidence]**. Fix: push "sign in now" at T−24 h. |

### 4.5 Credible schedule [Est]

| Milestone | Current team | +3 people and the §6 simplifications |
|---|---|---|
| P0 launch, live exams capped at 20,000 | Weeks 28–34 | Weeks 24–28 |
| First 200,000-candidate national exam | Launch + 6–10 weeks | Launch + 6–10 weeks |

**What would move the schedule**

| Factor | Effect |
|---|---|
| Verification status of the existing bank | ±6 weeks |
| D1 negative | Tutor launches without page citations, or with renegotiated scope |
| D3: handwriting fails the gate | Photo solve stays in beta |
| Merchant onboarding lead time | Payments slip |
| Android spike fails | +3–4 weeks |

---

## 5. Decision

### 5.1 Top five delivery risks

| # | Risk | Modules | Evidence | Consequence | Owner | Smallest validation | Pass/fail | Decide by |
|---|---|---|---|---|---|---|---|---|
| 1 | Content not verified in time | QB, CMS, PRAC, AI | 150,000-question assumption (§0.1); two-person rule (CMS-02); no reviewer staffing in §8.1 | Thin pilot content; tutor's bank grounding is weak; week 16 slips | Head of content | Inventory the bank; time 200 real questions through review and verification | Measured minutes × launch-track volume fits staffed reviewer hours by week 14 | Week 2 |
| 2 | Tutor quality and content rights | AI, QB | D1 and D3 open; no evaluation run yet | No page citations, or photo solve fails its gate at launch | AI/ML engineer + legal | 100-item shortlist evaluation, 50 consented handwriting photos, written answer on NCTB rights | Explanations ≥ 80% correct; photo expression exact match ≥ 70% before tuning; written permission or a legal opinion | D1 week 4; D3 week 10 |
| 3 | Exam correctness and scale unproven | EXAM, NFR, OFF | Gaps in §3.1 of this review; no measurement | Lost or mis-scored answers on a national exam | Platform engineer + EXAM lead | Fix the design; ingest prototype with fault injection at 20,000 simulated candidates | Ingest ≥ 1,500 requests per second per instance at p99 acknowledgement < 500 ms; zero acknowledged answers lost; contiguity check catches every injected gap | Week 8 (also settles D5) |
| 4 | Specialist capacity | All, especially AI, EXAM, NFR | §4.1 of this review | Week-24 launch slips 4–10 weeks | Engineering manager | Compare velocity at week 4 with the plan | Burn within 10% of plan, or hire and contract | Week 4 |
| 5 | Payments and Play policy | PAY, OFF | D2 open; bKash execute step **[Needs evidence]**; merchant lead times unknown | No revenue at launch, or a payment flow that breaks store policy | Product + PAY lead | Apply to bKash and the aggregator in week 1; get a Play policy opinion; build the sandbox flow | Sandbox credentials by week 6; written policy position | Week 6 |

### 5.2 Open decisions D1–D5: what each actually blocks

| Decision | Blocks | Does not block |
|---|---|---|
| D1: NCTB rights | Ingesting and citing textbook pages (AI-02, AI-02a); textbook citation in the week-6 slice | Gateway; bank-grounded explanations; evaluation harness; photo-solve flow |
| D2: payments on Android | Payment UI on Android; Play Billing integration; pricing and margins | Entitlement engine; web payments; bKash backend |
| D3: model quality | Model per route; photo-solve launch scope; cost model | All tutor infrastructure |
| D4: legal (consent, retention, residency) | Consent screens; collecting handwriting data from minors; production hosting region if residency is required (decide before production infrastructure, by week 4) | Development in the Mumbai region |
| D5: 200,000 at launch? | Order of exam-scale investment; launch-day exam cap | Exam core, blueprints, ingest design |

**Add three decisions:**

- **D6. Gamification rules:**
  - Which date or period late XP counts toward.
  - XP asymmetry when a key is corrected downwards.
  - Mistake Notebook removal on correction.
  - Minors on national boards.

  Decide by week 3.
- **D7. Live-exam closing policy:** the late window, two-phase close and publication time, and whether a provisional score is shown within 5 s. Decide by week 2.
- **D8. Content provenance:** rights to scanned guidebook and admission-paper questions. Decide by week 4.

### 5.3 First two weeks

**Build immediately**

- **Platform:** repository, CI, Terraform skeleton for development and staging; Postgres; a job queue in Postgres; outbox; event log to S3.
- **AUTH:** OTP sign-in with a test SMS adapter.
- **TAX and QB:** schema with versions and bilingual content; the SSC Physics tree.
- **PRAC:** session and answer API with ids scoped by user.
- **GAM:**
  - Reward ledger and streak engine.
  - The §5.5 scenario plus 20 edge cases written as tests first.
- **AI:**
  - Gateway skeleton with quotas, exam lock and moderation hooks.
  - "Why is X wrong" grounded on verified explanations.
  - Canonical cache keyed by content only.
- **Clients:** design system with bundled Bangla fonts; PWA shell; React Native exam-screen and question-renderer spike on a 2 GB Android 8.1 device.
- **Content:** one SSC Physics chapter of about 150 questions, verified blind by two people (in a spreadsheet if the CMS is not ready).

**Validate in parallel**

- OCR and model shortlist evaluation on 100 items (AI engineer + 2 teachers).
- Time-and-motion study on 200 bank questions.
- Legal requests for D1, D4 and D8.
- Play policy check (D2).
- bKash and aggregator merchant applications.
- Exam design fixes (§3.1) and the D7 decision.
- Gamification rules workshop (D6).

**Wait until before the pilot (weeks 3–16):** CMS editor, import pipeline, Banglish search, payments (live after the pilot), admin console, photo solve (beta), load tests at 20,000 and 50,000.

**Wait until before the national exam:** 250,000 rehearsal, the full control room, national-scale merit lists, the penetration test, multi-region restore drill.

The week-6 session keeps both pillars. The tutor answers "খ কেন ভুল?" with a verified citation, and the student earns XP, keeps the streak and gets the next-day reminder.

### 5.4 Requirement and milestone changes to decide explicitly

| Change | Impact |
|---|---|
| NFR-01: launch with live exams capped at 20,000; 200,000 after staged rehearsals | Lowers launch risk; national exam moves about 6–10 weeks after launch |
| NFR-02: for live exams, either a provisional score in 5 s without rank, or a documented 5 s receipt | Keeps NFR-02 honest; needs D7 |
| Week 16 pilot is free | Takes PAY off the pilot's critical path |
| AI-02a: if D1 fails, citations point to verified explanations and question ids only | Tutor launches with weaker grounding |
| AI-15: free-form semantic cache deferred to P1; canonical cache at P0 | Removes the privacy classifier; small cost increase |
| EXAM-06: institution rank labelled "self-reported" until rosters exist (INST, P1) | Prevents gamed rankings |
| Week 24: move to week 28 unless about 3 people are added by week 6 | Schedule realism |

---

## 6. Where the design can be simpler

You asked me to check everywhere the design could be simpler. Effort savings are **[Est]**.

| # | Simplification | Removes | P0 requirement impact | Saves (pw) | Risk |
|---|---|---|---|---|---|
| S1 | Write the Mistake Notebook, topic progress and XP ledger **synchronously** in the answer transaction. All are in the same database and process. Use a savepoint so a reward failure never fails the answer. Keep events for the warehouse, leaderboards and notifications. | Asynchronous projection consumers for core learning state; the duplicate `xp_preview` path; most eventual-consistency bugs | None | 2–3 | GAM bugs sit closer to the answer path. The savepoint covers it. |
| S2 | Use a **Postgres job queue** (`SKIP LOCKED`) for all non-exam background work. Keep SQS only for exam ingest. | One managed queue, its IAM and its dead-letter handling for most jobs | None | 1–2 | Revisit above about 1,000 jobs per second |
| S3 | **Drop ClickHouse at P0.** Event log as Parquet on S3; query with DuckDB or Athena. | A database to run and load | NFR-09 met by the S3 log plus a query engine | 2–3 | Slower BI queries. Add ClickHouse when dashboards need it. |
| S4 | One learner UI codebase: **React Native plus react-native-web**. Admin and CMS stay in React. | Two learner front ends | None | 8–12 (client) | Web bundle and performance. Validate in the week-2 spike against the 170 KB and BD-3G targets. |
| S5 | AI at P0: one provider plus a kill switch, with failover meaning verified explanations; canonical cache only; no transliteration step; no reranker; a single OCR read plus the confirm step | Failover routing, privacy classifier, transliteration model, reranker service, double OCR cost | AI-15 free-form semantic cache moves to P1 (decide) | 3–5 (AI/ML) | Lower peak quality. The evaluation decides whether the reranker returns. |
| S6 | **Buy** the helpdesk (OPS-02); use a static site or headless CMS for blog and SEO (OPS-03); build the admin console on an admin framework | Ticketing, CMS, much of the console UI | None | 3–5 | Vendor needs Bangla support **[Needs evidence]** |
| S7 | Gamification rules: boards by receipt time, streaks by effective date; no freeze refunds (settlement at 06:00 is final); daily cap only, no rapid-guess rule at P0 (flag offline instead) | Reversal paths and two ambiguous rules | None | 1 | Slightly less fair to edge cases |
| S8 | Exam at P0: one paper set × 2 languages (sets are EXAM-09, P1); append-only answer log with one batch in flight per client | Multi-set logic; the sequence-gap ambiguity | None | 1 (and fixes correctness) | None |
| S9 | Launch-day exam cap of 20,000 (D5) | 250,000 rehearsals before launch | NFR-01 milestone moves (decide) | 4–6 (platform and QA before launch) | Pushes the national exam later |
| S10 | Search at P0: Bangla normalisation, phonetic folding, trigram and embeddings, **no custom stemmer** | A stemmer to build and maintain | NFR-04 "stemming" partly deferred (decide), unless trigram plus embeddings pass the 500-query gate | 1–2 | Recall on inflected words. Measure first. |
| S11 | Defer email and password sign-in (optional in AUTH-01) | One sign-in method | AUTH-01 lists it as optional | 0.5 | Low |
| S12 *(evaluate, not adopted)* | Exam ingest writes each batch straight to DynamoDB, acknowledging after the write, instead of SQS plus consumers | Consumer fleet and Postgres upsert load | None | Possibly 2–3 | Adds a datastore. Decide in the week-6 ingest spike. |

**Total savings: about 25–40 person-weeks.** With S1–S11 plus the staffing changes in §4.1, the week 24–28 range becomes credible.

**Do not simplify these. They protect correctness and trust:**

- Attempts pinned to a question version.
- Idempotency keys scoped by user.
- The outbox and event log from day one (NFR-09).
- Exam answers saved on the device, then acknowledged only after durable storage.
- Blind two-person key verification.
- Server-enforced tutor lockout during live exams.
- `tenant_id` from day one.
- Minors' privacy defaults.

---

## Verification of this review

- Every quoted design statement was checked by search against `docs/system-design.md` (passages at lines 460, 495–509, 582, 663, 680, 732–770, 784, 813, 875–885, 943, 1086).
- The arithmetic in §3.2, §4.3 and §4.4 is shown inline and can be recomputed.
- Claims marked **[Needs evidence]** are not verified. The main ones are bKash Execute Payment, Play policy for Bangladesh, settlement report APIs, SQS FIFO quotas, Python ingest throughput and Bangladeshi SMS throughput.

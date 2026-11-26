# Unified Bangladesh Practice + AI Tutor Platform: Feature Requirements

**Scope:** Class 6–12 (all groups and versions), university admission, government/bank job preparation, AI tutor
**Version:** v1.0 · 2026-11-25

**Priority legend**

| Tag | Meaning |
|---|---|
| **P0** | Needed for launch |
| **P1** | Soon after launch |
| **P2** | Later |

---

## Table of Contents
1. [Identity & Accounts (AUTH)](#1-identity--accounts-auth)
2. [Curriculum & Taxonomy (TAX)](#2-curriculum--taxonomy-tax)
3. [Question Bank & Content Model (QB)](#3-question-bank--content-model-qb)
4. [Content Management System (CMS)](#4-content-management-system-cms)
5. [Practice Engine (PRAC)](#5-practice-engine-prac)
6. [Exam Engine (EXAM)](#6-exam-engine-exam)
7. [Analytics & Progress (ANL)](#7-analytics--progress-anl)
8. [AI Tutor (AI)](#8-ai-tutor-ai)
9. [Gamification (GAM)](#9-gamification-gam)
10. [Planner, Calendar & Alerts (PLAN)](#10-planner-calendar--alerts-plan)
11. [Community & Doubt Support (COM)](#11-community--doubt-support-com)
12. [Parent Portal (PAR)](#12-parent-portal-par)
13. [Institution / Teacher / Coaching Center (INST)](#13-institution--teacher--coaching-center-inst)
14. [Commerce & Payments (PAY)](#14-commerce--payments-pay)
15. [Offline, Performance & Device Support (OFF)](#15-offline-performance--device-support-off)
16. [Support, Admin & Ops (OPS)](#16-support-admin--ops-ops)
17. [Platform & Non-Functional (NFR)](#17-platform--non-functional-nfr)
18. [Suggested Build Order](#18-suggested-build-order)

---

## 1. Identity & Accounts (AUTH)

| ID | Pri | Feature |
|---|---|---|
| AUTH-01 | P0 | Phone OTP sign-up/login (+88), Google login, optional email/password |
| AUTH-02 | P0 | Device/session management; a single active session can be enforced during live exams |
| AUTH-03 | P0 | Roles: Student, Parent, Teacher, Institution Admin, Content Author, Reviewer, Ops Admin, Super Admin (fine-grained permissions per role) |
| AUTH-04 | P0 | Student profile: name, photo, class, group (Science / Business Studies / Humanities), version (Bangla/English), curriculum (General / Madrasah / Technical), institution, district/upazila, board, exam year |
| AUTH-05 | P0 | Multi-track enrolment on one account, e.g. "HSC Science 2028" + "Medical Admission 2028", later "BCS" |
| AUTH-06 | P1 | Track promotion flow (Class 10 → SSC → HSC → Admission → Job) with history preserved across tracks |
| AUTH-07 | P1 | Parent–child linking via invite code or QR; one parent can have many children |
| AUTH-08 | P1 | Multiple student profiles on one shared device, each with a PIN |
| AUTH-09 | P1 | Institution enrolment via join code, CSV upload or roll-number import |
| AUTH-10 | P2 | Under-18 parental consent flow; account deletion and data export |

## 2. Curriculum & Taxonomy (TAX)

| ID | Pri | Feature |
|---|---|---|
| TAX-01 | P0 | Configurable hierarchy: Track → Exam/Class → Group/Unit → Subject → Paper → Chapter → Topic → Sub-topic/Skill |
| TAX-02 | P0 | Academic tracks: Class 6–8, SSC (9–10), HSC (11–12), all groups |
| TAX-02a | P0 | Admission tracks: DU units, GST cluster, Engineering, Medical/Dental, Agri cluster, other public universities, BUP, AFMC, Nursing, National University, private universities |
| TAX-02b | P0 | Job tracks: BCS Prelim/Written/Viva, Bank, Primary, NTRCA, 9th–20th grade, Police/Defence/NSI, others |
| TAX-03 | P0 | Syllabus versioning by year; one question can map to several syllabus versions |
| TAX-04 | P0 | Bangla and English names for every node; ordering; icons; free/paid flag per node |
| TAX-05 | P1 | Madrasah (Dakhil/Alim) and Technical (BTEB) trees |
| TAX-06 | P1 | Cross-track topic links (e.g. HSC Physics Ch 4 ≈ Admission "Newtonian Mechanics" ≈ BCS General Science); mastery is shared across linked topics |

## 3. Question Bank & Content Model (QB)

| ID | Pri | Feature |
|---|---|---|
| QB-01 | P0 | Objective question types: MCQ (single), multi-statement MCQ (i/ii/iii), stimulus-based/situational MCQ |
| QB-01a | P0 | Written question types: CQ/সৃজনশীল (stem + ক/খ/গ/ঘ with marks), short answer, written/essay |
| QB-01b | P0 | Other question types: fill-in-blank, true/false, matching, numeric answer |
| QB-02 | P0 | Rich content: Bangla + English Unicode, LaTeX math (Bangla numerals optional), chemistry formulas, tables, images, SVG diagrams, audio (English listening) |
| QB-03 | P0 | Metadata per question: taxonomy nodes; source (board/year/school/university/unit/BCS number/exam name); difficulty (author-set + computed); Bloom/CQ level; marks; time estimate; version (language); tags; status |
| QB-04 | P0 | Answer key, detailed explanation, optional video explanation URL, linked concept note |
| QB-05 | P0 | Translations: paired Bangla/English versions of the same question |
| QB-06 | P0 | Full version history per question; edits never break past attempts (attempts store the version id) |
| QB-07 | P0 | Bulk import from Excel/CSV/Word/JSON with a validation report |
| QB-07a | P0 | PDF/image import using Bangla + math OCR, followed by a human review queue |
| QB-08 | P0 | Duplicate/near-duplicate detection on import (text + math normalisation + embeddings) |
| QB-09 | P0 | Previous-year paper object: a complete original paper (board/year/unit) that can be taken as an exam or browsed |
| QB-10 | P1 | Question families/variants (same concept, different numbers) for anti-cheat and repeated practice |
| QB-11 | P1 | Item statistics: p-value (difficulty), discrimination index, distractor selection %, average time, auto-flag for "probably wrong key" |
| QB-12 | P1 | Concept notes, cheat sheets and formula sheets per topic |
| QB-13 | P1 | Flashcard decks (auto-generated from facts, e.g. BCS GK) plus user-made decks |
| QB-14 | P1 | Current-affairs feed for jobs: daily items, auto-generated quizzes, monthly compilation |

## 4. Content Management System (CMS)

| ID | Pri | Feature |
|---|---|---|
| CMS-01 | P0 | WYSIWYG question editor with live LaTeX/Bangla preview and mobile preview |
| CMS-02 | P0 | Workflow: Draft → In Review → Verified → Published → Retired; answer keys need two-person verification |
| CMS-03 | P0 | Role-based access per subject/track; assignment queues for authors and reviewers |
| CMS-04 | P0 | Error-report queue from students, with triage and SLA |
| CMS-04a | P0 | Error resolution: auto-notification to affected users and score re-computation |
| CMS-05 | P0 | Search and filter the bank by any metadata; bulk edit/tag/move |
| CMS-06 | P0 | Exam blueprint builder (see EXAM-01) |
| CMS-07 | P1 | AI-assisted authoring: draft explanations, generate variants, translate BN↔EN, auto-tag taxonomy, detect a likely-wrong key. Everything requires human approval |
| CMS-08 | P1 | Content coverage dashboard: questions per chapter/type/difficulty, gaps highlighted |
| CMS-09 | P1 | Author productivity and payment tracking (freelancers) |
| CMS-10 | P2 | Media library with CDN, image compression and alt-text |

## 5. Practice Engine (PRAC)

| ID | Pri | Feature |
|---|---|---|
| PRAC-01 | P0 | Custom practice builder: subjects/chapters/topics, count, time limit, difficulty, source filter (board/admission/BCS/year), question type, negative marking on/off |
| PRAC-02 | P0 | Two feedback modes: Learn (answer shown immediately) and Test (answers revealed at the end) |
| PRAC-03 | P0 | Chapter-wise and topic-wise practice; textbook-exercise mode (মূলবই) |
| PRAC-04 | P0 | Previous-year paper practice (board-wise, year-wise, unit-wise) |
| PRAC-05 | P0 | Mistake Notebook: wrong/skipped questions added automatically; re-practice; a question is cleared after 2 correct answers in a row |
| PRAC-06 | P0 | Bookmarks with folders; personal notes on any question |
| PRAC-07 | P0 | "Report error" on every question (wrong key, typo, wrong explanation, out of syllabus) |
| PRAC-08 | P1 | Adaptive practice: per-topic ability estimate (IRT/Elo); next question chosen to stay at 60–75% success |
| PRAC-09 | P1 | Spaced repetition (FSRS/SM-2) for mistakes and flashcards; due-review queue |
| PRAC-10 | P1 | Daily Mix: auto-generated daily set built from weak topics, due reviews and new material |
| PRAC-11 | P1 | Speed drill mode with a per-question timer and speed analytics |
| PRAC-12 | P1 | Diagnostic test per track at onboarding; seeds the mastery map |
| PRAC-13 | P2 | 1v1 real-time quiz duel (friend/random); group quiz rooms (Kahoot-style) for classrooms |

## 6. Exam Engine (EXAM)

| ID | Pri | Feature |
|---|---|---|
| EXAM-01 | P0 | Exam blueprint: sections, subjects, question count per chapter/difficulty, marks, negative marking (e.g. 0.25/0.5), section time limits, total time, optional sections, pass marks. Pre-built for each real exam |
| EXAM-02 | P0 | Exam types: practice mock (auto-generated from blueprint), fixed model test, live exam (scheduled national), previous-year paper, institution/batch exam |
| EXAM-03 | P0 | Exam UI: question palette, mark-for-review, OMR-sheet view, section switcher, timer, low-time warnings, auto-submit, calculator (if the exam allows one) |
| EXAM-04 | P0 | Live exam, before start: listing, registration, fee (if paid), reminders, countdown, paper locked until start |
| EXAM-04a | P0 | Live exam, during and after: synchronised start, late-entry rules, auto-submit at end, result publish time, solution unlock time |
| EXAM-05 | P0 | Answer persistence: every response saved locally and synced; resume after disconnect/app kill; server-authoritative timer |
| EXAM-06 | P0 | Merit list: national, district, institution and group rank; tie-break rules; publish/unpublish control; downloadable list |
| EXAM-07 | P0 | Result page: score, correct/wrong/skipped, negative-mark loss, time, rank, percentile, comparison with topper and average, per-question solutions |
| EXAM-08 | P0 | Re-attempt (counts for practice, not rank) and review mode |
| EXAM-09 | P1 | Anti-cheat, paper side: question/option shuffle, per-user variants, single device |
| EXAM-09a | P1 | Anti-cheat, device side: app-switch/tab-blur detection with logs, screenshot/screen-record blocking (Android FLAG_SECURE) |
| EXAM-09b | P1 | Anti-cheat, analysis side: IP/device anomaly flags, answer-similarity collusion detection, admin review console |
| EXAM-10 | P1 | Written exam submission: upload photos/PDF of handwritten answers per question; graded by AI (AI-07) and/or a human examiner (with a rubric UI) |
| EXAM-11 | P1 | Exam series/packages (e.g. "30 Live Exams for DU B Unit") with a schedule and a cumulative leaderboard |
| EXAM-12 | P1 | Certificates (PDF with verification QR) for live-exam toppers and series completion |
| EXAM-13 | P2 | Admission/job score predictor from historical cut-offs ("estimated position") |
| EXAM-14 | P2 | Proctored mode (front-camera snapshots at random intervals) for institution exams that need it |

## 7. Analytics & Progress (ANL)

| ID | Pri | Feature |
|---|---|---|
| ANL-01 | P0 | Student dashboard: readiness score per track; accuracy by subject → chapter → topic; attempts, study time, streak |
| ANL-02 | P0 | Exam history with trends (score over time, rank over time) |
| ANL-03 | P0 | Weak-area list (top N weakest topics) with one-tap practice |
| ANL-04 | P1 | Mastery map: a level for every topic (Not started / Learning / Proficient / Mastered), shown as a heatmap |
| ANL-05 | P1 | Time analytics: time per question vs accuracy, rushed/slow patterns, guess detection, marks lost to negative marking |
| ANL-06 | P1 | Previous-year trend analytics: chapter-wise frequency heatmap across boards/years/units, "most-asked topics", "predicted important topics" |
| ANL-07 | P1 | Peer percentile within the same track, exam year and district |
| ANL-08 | P1 | Readiness forecast to the exam date based on current pace |
| ANL-09 | P2 | Exportable progress report PDF (for parents/teachers) |

## 8. AI Tutor (AI)

| ID | Pri | Feature |
|---|---|---|
| AI-01 | P0 | Chat tutor: Bangla/English/Banglish input; context-aware (class, group, version, track, current chapter, recent mistakes); conversation history; new chat per subject |
| AI-02 | P0 | Grounded answers (RAG) over NCTB textbooks, the question bank, explanations and notes |
| AI-02a | P0 | Citations on every answer (book, chapter, page / question id); says "not sure" when it cannot find support |
| AI-03 | P0 | Photo solve: camera/gallery capture, crop, OCR (Bangla + English + math + diagrams); step-by-step solution, concept named, 3 similar questions from the bank |
| AI-04 | P0 | "Explain" actions on every question/solution: explain simpler, why is option X wrong, give an example, explain in Bangla/English, show a shortcut/trick |
| AI-05 | P0 | Guardrails: education-only topic limits, child-safe moderation, AI disabled during live exams |
| AI-05a | P0 | Usage limits and feedback: per-plan daily quotas, rate limiting, thumbs up/down with reason, flagged answers go to a review queue |
| AI-06 | P1 | Tutor modes: Socratic/hint mode (doesn't reveal the answer at once) and direct solution mode; parents/teachers can lock the mode |
| AI-07 | P1 | Written-answer grader, input: student types or photographs a handwritten answer |
| AI-07a | P1 | Grader rubrics: CQ levels (ক/খ/গ/ঘ marking); BCS Written (essay, composition, translation, math); SSC/HSC English writing (paragraph, letter, essay, email) |
| AI-07b | P1 | Grader output: score, rubric breakdown, missing points, model answer, rewrite suggestions |
| AI-08 | P1 | Quiz generator from any topic, or from uploaded notes/photo; items labelled "AI" and kept apart from the verified bank |
| AI-09 | P1 | Chapter summariser: short notes, key points, formula list, mind-map outline, "last-night revision" sheet |
| AI-10 | P1 | AI study coach: weekly plan from exam date, mastery map and available hours; re-plans when days are missed; daily nudges |
| AI-11 | P1 | Mistake diagnosis: clusters wrong answers into misconceptions and assigns a targeted fix set |
| AI-12 | P2 | Voice: Bangla speech-to-text for questions; TTS read-out of explanations |
| AI-13 | P2 | Spoken English partner (conversation practice with pronunciation feedback) |
| AI-14 | P2 | Viva/interview simulator (BCS viva, BUP/AFMC interviews) with scored feedback |
| AI-15 | P0 | AI infrastructure, routing and cost: model router (cheap model for simple queries, strong model for solving/grading), semantic answer cache, per-user cost tracking |
| AI-15a | P0 | AI infrastructure, quality: prompt/version management, offline evaluation set per subject |

## 9. Gamification (GAM)

| ID | Pri | Feature |
|---|---|---|
| GAM-01 | P0 | XP for each activity, levels, daily goal |
| GAM-02 | P0 | Daily streak with streak freeze |
| GAM-03 | P0 | Leaderboards: weekly/monthly/all-time × national/district/institution/friends, per track |
| GAM-04 | P1 | Badges and achievements (configurable rules engine) |
| GAM-05 | P1 | Weekly leagues with promotion/relegation |
| GAM-06 | P1 | Challenges/events with a time window, goals and rewards (e.g. "SSC 30-day challenge") |
| GAM-07 | P1 | Shareable cards (result, streak, rank) as images for Facebook/WhatsApp/Instagram, with a referral link built in |
| GAM-08 | P2 | Rewards store: XP → AI credits, discounts, merchandise |
| GAM-09 | P2 | Friends/follow system; institution-vs-institution team leagues |

## 10. Planner, Calendar & Alerts (PLAN)

| ID | Pri | Feature |
|---|---|---|
| PLAN-01 | P0 | Exam countdown per track |
| PLAN-02 | P0 | Notification center plus push (FCM/APNs): streak, live-exam reminders, results, new content, payment |
| PLAN-03 | P1 | Study routine/calendar (manual or generated by AI-10) with reminders |
| PLAN-04 | P1 | Circular & exam-date tracker (admission and jobs): application windows, admit cards, exam dates, results |
| PLAN-04a | P1 | Tracker follow-and-alert: students follow exams and get alerts; admins manage the data |
| PLAN-05 | P1 | Eligibility checker: rules engine using GPA/year/group/age/subject; shows eligible universities, units and jobs |
| PLAN-06 | P1 | SMS channel (Bangla) for critical alerts |
| PLAN-07 | P2 | WhatsApp/Telegram notification channel; Google Calendar export |

## 11. Community & Doubt Support (COM)

| ID | Pri | Feature |
|---|---|---|
| COM-01 | P1 | Per-question discussion threads: moderated, upvotes, "verified teacher" answers pinned |
| COM-02 | P1 | Human doubt escalation (paid): AI hands off to a mentor queue with an SLA; mentors reply by text, image or voice |
| COM-03 | P2 | Subject Q&A forum |
| COM-04 | P2 | Study groups/batch chat with minor-safety controls (no DMs between minors and unknown adults; reporting; moderation) |
| COM-05 | P0 | Moderation tools: profanity filter (BN/EN), report, mute, ban, audit |

## 12. Parent Portal (PAR)

| ID | Pri | Feature |
|---|---|---|
| PAR-01 | P1 | Child overview: study time, streak, exams taken, scores, rank trend, weak subjects |
| PAR-02 | P1 | Weekly report via app and Bangla SMS |
| PAR-03 | P1 | Controls: AI tutor mode lock, daily time cap, quiet hours |
| PAR-04 | P1 | Pay for a child's subscription; family plan |
| PAR-05 | P2 | Alerts (e.g. "no study for 3 days", "score dropped") |

## 13. Institution / Teacher / Coaching Center (INST)

| ID | Pri | Feature |
|---|---|---|
| INST-01 | P1 | Institution workspace: logo/branding, branches, teachers, batches/sections |
| INST-02 | P1 | Student roster management (invite, CSV, roll number); seat/licence allocation |
| INST-03 | P1 | Exam creation from the platform bank and/or the institution's private bank (private questions stay private) |
| INST-04 | P1 | Batch exam scheduling (online), with results and merit list within the batch |
| INST-05 | P1 | Mobile OMR scanning: printable OMR sheet generator, phone-camera scan, auto-grade, results synced to student accounts |
| INST-06 | P1 | Question paper generator: print-ready PDF with Bangla typesetting, sets A/B/C/D, answer key, institution header |
| INST-07 | P1 | Analytics per batch/student: weak chapters, participation, comparison between batches |
| INST-08 | P1 | Assignments/homework with due dates; written submissions; AI-assisted grading (AI-07) with teacher override |
| INST-09 | P2 | Teacher marketplace: teachers publish paid exam series or notes; revenue share; payouts |
| INST-10 | P2 | White-label subdomain/app for large coaching chains |
| INST-11 | P2 | Attendance and basic fee tracking (light LMS) |

## 14. Commerce & Payments (PAY)

| ID | Pri | Feature |
|---|---|---|
| PAY-01 | P0 | Product catalog: track passes, exam series, single exams, AI credit packs, institution licences; validity in days or until an exam date |
| PAY-02 | P0 | Entitlement engine: content/feature gating by product, free quotas (questions/day, AI messages/day, live exams/week), trials |
| PAY-03 | P0 | Payment gateways: bKash, Nagad, Rocket, Upay; cards via SSLCommerz/aamarPay; Google Play Billing / Apple IAP where required |
| PAY-04 | P0 | Coupons/promo codes, referral credits, invoices/receipts (PDF, SMS) |
| PAY-05 | P0 | Refund handling, payment reconciliation, webhook retries, failed-payment recovery |
| PAY-06 | P1 | Auto-renew subscriptions (where the gateway supports tokenisation); family plan; bundles; upgrade/downgrade with proration |
| PAY-07 | P1 | Affiliate/campus ambassador program with tracking links and payout reports |
| PAY-08 | P2 | Scholarships/sponsored seats (funded by NGOs or corporates) |

## 15. Offline, Performance & Device Support (OFF)

| ID | Pri | Feature |
|---|---|---|
| OFF-01 | P0 | Android app (Android 8+, runs well on 2–3 GB RAM devices, APK under ~30 MB) plus a responsive web/PWA |
| OFF-02 | P0 | Lite mode: no images unless tapped; compressed payloads |
| OFF-03 | P1 | Offline practice packs: download chapters, practise offline, sync results later (with conflict handling) |
| OFF-04 | P1 | iOS app |
| OFF-05 | P2 | Desktop-friendly web exam mode for institutions (lab exams) |

## 16. Support, Admin & Ops (OPS)

| ID | Pri | Feature |
|---|---|---|
| OPS-01 | P0 | Admin console: users, subscriptions, manual entitlement grant, refunds |
| OPS-01a | P0 | Live-exam control room: live participant count, incidents, extend time, invalidate a question |
| OPS-02 | P0 | In-app support ticketing (Bangla), FAQ/help center, call/WhatsApp links |
| OPS-03 | P0 | CMS for banners, announcements, notices, blog/SEO pages |
| OPS-04 | P0 | Audit logs for all admin actions |
| OPS-05 | P1 | Campaign tools: segmented push/SMS/email by track/class/district/plan; A/B testing |
| OPS-06 | P1 | Business analytics: DAU/WAU, funnels, conversion, retention by track, revenue, AI cost per user |
| OPS-07 | P1 | Feature flags and remote config |

## 17. Platform & Non-Functional (NFR)

| ID | Pri | Requirement |
|---|---|---|
| NFR-01 | P0 | Live-exam scale target: 200k concurrent users with a synchronised start; load-tested before every major exam |
| NFR-01a | P0 | Live-exam scale design: papers pre-generated and served from CDN/edge; submissions go through a queue; rank computation runs as a batch job |
| NFR-02 | P0 | Latency: question load under 300 ms on 3G; result shown under 5 s after submit (merit list may be deferred) |
| NFR-03 | P0 | Availability: 99.9%; zero-data-loss answer persistence; graceful degradation (AI down ≠ practice down) |
| NFR-04 | P0 | Search: Bangla-aware full-text search (stemming, spelling variants, phonetic/Banglish), math-normalised and semantic (vector) search over questions |
| NFR-05 | P0 | Localisation: full BN/EN UI, Bangla numerals/dates, Unicode only, Bangla fonts bundled |
| NFR-06 | P0 | Security: OWASP Top 10, rate limiting, OTP abuse protection, encrypted PII |
| NFR-06a | P0 | Content protection: signed content URLs to protect the question bank from scraping; scraping detection |
| NFR-07 | P0 | Privacy for minors: leaderboards show first name + institution only, opt-out, no public phone numbers, parental consent, data retention policy |
| NFR-08 | P0 | Observability: crash/ANR reporting, APM, structured logs, alerting, live-exam dashboards |
| NFR-09 | P0 | Analytics event pipeline (every attempt/answer/time-spent event) into a warehouse; feeds item stats, adaptivity, recommendations, BI. Build from day one |
| NFR-10 | P1 | Multi-region backups, point-in-time recovery, disaster recovery runbook |
| NFR-11 | P1 | Accessibility: font scaling, high contrast, screen reader labels |

---

## 18. Suggested Build Order

| Step | Modules | Milestone |
|---|---|---|
| 1 | TAX + QB + CMS (with bulk import) | Existing question bank ingested, tagged, verified |
| 2 | AUTH + PRAC + EXAM + PAY | **MVP**: the product starts earning money |
| 3 | ANL + GAM | Students can see progress and keep up study habits |
| 4 | AI-01 to AI-05, AI-15 | AI tutor launch |
| 5 | AI P1 (grader, coach, Socratic) + PLAN | Main differentiators live |
| 6 | PAR | Parent portal |
| 7 | INST | B2B revenue (coaching centers and schools) |
| 8 | All P2 items | Expansion |

> **Note:** NFR-09 (event pipeline) must be in place from day one. Adaptivity, item statistics and the AI coach all need historical attempt data, and they can't use data that was never recorded.

---

## Feature Count Summary

| Module | P0 | P1 | P2 | Total |
|---|---|---|---|---|
| AUTH | 5 | 4 | 1 | 10 |
| TAX | 6 | 2 | 0 | 8 |
| QB | 12 | 5 | 0 | 17 |
| CMS | 7 | 3 | 1 | 11 |
| PRAC | 7 | 5 | 1 | 13 |
| EXAM | 9 | 6 | 2 | 17 |
| ANL | 3 | 5 | 1 | 9 |
| AI | 9 | 8 | 3 | 20 |
| GAM | 3 | 4 | 2 | 9 |
| PLAN | 2 | 5 | 1 | 8 |
| COM | 1 | 2 | 2 | 5 |
| PAR | 0 | 4 | 1 | 5 |
| INST | 0 | 8 | 3 | 11 |
| PAY | 5 | 2 | 1 | 8 |
| OFF | 2 | 2 | 1 | 5 |
| OPS | 5 | 3 | 0 | 8 |
| NFR | 11 | 2 | 0 | 13 |
| **Total** | **87** | **70** | **20** | **177** |

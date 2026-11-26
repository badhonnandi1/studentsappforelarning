# Product strategy: teacher-checked written marks

**Date:** 2026-11-26 · **Basis:** [market validation](market-validation.md). Nothing here has been tested with users yet.

## 1. Position

**A student writes a creative question (CQ) answer by hand. The app drafts marks for each part and shows why. A teacher checks them. The app publishes how often its drafts agree with teachers.**

| For | Promise |
|---|---|
| Teacher or coaching centre | Check a batch's written answers from a prepared draft instead of from a blank page |
| Student | Marks and a reason for each part, labelled "teacher checked" or "practice estimate" |
| Guardian | The marks are a teacher's, and no sales calls |

The time saved for teachers is the claim to prove. It has not been measured.

## 2. Why this, and not the other options

| Evidence | Meaning |
|---|---|
| Written answers carry most theory marks ([§2.1](market-validation.md)) | The practice that matters most is the hardest to get marked |
| Oddhoyon and Utsaho already claim AI marking of photographed answers | Marking alone does not stand out |
| No commercial app seen publishes marking accuracy | Measured trust is open |
| Teacher tools found in Bangladesh stop at multiple-choice sheets, fees and attendance | Written marking for a batch is open |
| England's exam regulator treats AI as the sole marker as non-compliant ([Ofqual, Jan 2026](https://assets.publishing.service.gov.uk/media/696503ebe8b93f59c3aecce6/Principles_of_AI_use_in_marking_.pdf)). It does not govern Bangladesh | A teacher in the loop is the defensible design |
| Funded brands compete for students directly | Reaching students through their teacher avoids that contest. Whether teachers will bring them is untested |

| Option considered | Why not first |
|---|---|
| Madrasah (Dakhil, Alim) done properly | Utsaho already lists madrasah board questions; payment evidence not found; needs separate content |
| Re-sit packs for failed subjects | Short season, re-registration numbers unknown, easy for established apps to add |
| Another all-in-one student app | Every feature exists already |

Both stay possible later: syllabus tracks are data, not code.

## 3. First release

**Cohort:** SSC 2028. **Subjects:** physics, plus one humanities subject chosen with the pilot teachers.

| In | Requirement |
|---|---|
| Photo of a handwritten answer, checked for readability before marking | AI-07 |
| Rubric per part, written by a subject teacher | AI-07a (CQ only; BCS and English writing stay later) |
| Draft marks per part, the answer text behind each mark, missing points, model answer | AI-07b |
| Teacher review queue; the teacher's mark is final | AI-07c |
| Accuracy report per subject and part, visible in the app | AI-07d |
| Teacher batch: join code, set a written task, collect answers | INST-02a |
| Verified question bank for the chosen subjects, Mistake Notebook, streak, reliable exam submit | Existing P0 |

**Later:** admission and job content, institution workspaces, guardian reports, madrasah and vocational content, national exams beyond the 20,000 launch cap.

The reason shown for a lost mark is the rubric point and a verified explanation. A textbook page is added only with a licence (D1): the NCTB Act 2018 gives the Board copyright in its textbooks ([s.16(2)](http://bdlaws.minlaw.gov.bd/act-print-1275.html)), and some higher-secondary books come from other publishers.

## 4. Marking method

The method follows early research, mostly preprints on other languages ([§5](market-validation.md)). It must be proven on our own scripts.

1. Check the photo (blur, rotation, crop) and ask for a retake.
2. Test two routes on the same scripts: marks from the image, and marks from a word-for-word transcript. The transcriber must not correct the student. Ship the better route. Check digits separately.
3. Mark each part against its own rubric and quote the answer text behind every mark. Part count and marks come from data: higher mathematics and accounting used three parts, not four, in the 2017 higher-secondary structure.
4. Treat the student's writing as data. Flag text that reads as an instruction to the marker.
5. Repeat the run. Disagreement, poor reading, flags and boundary marks go to a teacher first. Agreement between runs does not prove a mark is right.
6. Record model and prompt version on every mark.

**Cost per answer** [Assumption, not measured]: top model, 4,500 tokens in and 2,000 out at $4 and $20 per million is $0.058, about Tk 7. Three runs are about Tk 21. Ten answers a month is about Tk 210 per student, close to a competitor's whole monthly plan (Tk 149 to 249). The test must also find the cheapest model and run count that passes.

## 5. Tests and gates

**Test 1: accuracy, in the first 4 weeks, before any marking feature is built.**

- At least 400 real answers per subject, from many students and several schools. About 385 independent items give ±5 points on an agreement percentage at 95% confidence; answers from the same student are not independent, so compute intervals by resampling students and questions.
- Two teachers mark each answer without seeing each other or the AI. A senior teacher settles differences.
- Report per part and per total: exact and within-one agreement, average error, bias, quadratic weighted kappa (QWK), large errors, share sent to a teacher, and results by handwriting, phone and mark band.

| Result | What ships |
|---|---|
| QWK against the settled mark at least 0.70, no more than 0.10 below teacher-to-teacher, bias at most 0.15 standard deviations | Drafts for teacher review |
| QWK at least 0.8, also passing the row above, per subject | Also a "practice estimate" for students without a teacher |
| Below the first row | No AI marks. If no subject passes, AI-07 to AI-07d and INST-02a return to P1; reconsider the plan before spending more |

The 0.70, 0.10 and 0.15 values are an assessment-industry convention seen second-hand ([ETS](https://www.ets.org/Media/Research/pdf/RM-23-01.pdf)); confirm before relying on them.

**Test 2: demand, same 4 weeks.** Interview 10 teachers and 30 students. Give at least 3 teachers hand-checked drafts for their own batches. Pass (proposed): drafts cut their marking time, they ask to continue, and at least one pays.

**Test 3:** legal opinion on textbook use (D1), minors' data and handwriting collection (D4).

Collecting answers needs guardian consent. Do not train commercial models on datasets licensed for non-commercial use, such as BanglaWriting (CC BY-NC).

## 6. What could sink it

| Risk | Note |
|---|---|
| AI cannot read Bangla handwriting well enough | No published figure for current models. One 2025 benchmark showed a general model far behind a specialised one |
| Teachers will not pay or change habits | No willingness-to-pay evidence found |
| Draft Education Act would phase out coaching centres in 3 to 5 years and stop teachers' private tutoring | Not passed. Sell to schools as well as coaching centres; watch the bill |
| Competitors copy it | An open-source demo already does per-part marking with teacher release. The lead is the measured data and teacher relationships, which take time to copy |
| More scope in the same time | Six requirements were added to P0 and the week-28 plan was not re-estimated. Re-check at the week-4 velocity review |

## 7. Open questions

- TODO(ask): is the existing question bank real and verified?
- TODO(ask): are the 10-engineer team and budget real, and when does building start?
- TODO(ask): which teachers or coaching centres can join the test?
- Price per teacher and per student: set after test 2.

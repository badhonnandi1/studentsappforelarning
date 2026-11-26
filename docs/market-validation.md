# Market validation: will the app stand out?

**Date:** 2026-11-26 · **Basis:** desk research (press, store listings, vendor sites). No student, teacher or parent interviews and no hands-on testing of competitor apps.

## 1. Verdict

**As designed, no.** AI tutor, photo solve, question bank, mock exams, streaks and leaderboards already exist in Bangladeshi apps. The design's real differences (verified keys, page citations, correct offline streaks, exam durability) are quality claims that a student cannot see in a store listing and that nobody has measured yet.

**It can stand out** with a narrower first product (§6).

## 2. Fit with the education system

| Fact | Effect on the design |
|---|---|
| New primary and secondary curriculum announced for 2028 ([TBS](https://www.tbsnews.net/bangladesh/education/new-curriculum-be-introduced-2028-not-2027-education-minister-1477336)). Which classes start first is not confirmed. | Syllabus versioning (TAX-03) is needed. Content tagged now for the lower classes may go stale. Start with cohorts furthest from the change. |
| SSC 2027: 7 Jan to 6 Feb 2027. HSC 2027: 6 June to 13 July. Government wants both moved to December later ([TBS](https://www.tbsnews.net/bangladesh/education/ssc-exams-begin-7-jan-hsc-19-june-next-year-1439201), [Daily Star](https://www.thedailystar.net/news/education/news/ssc-exams-begin-jan-7-hsc-june-6-next-year-4176216)) | If building starts the week of 30 Nov 2026, the week-16 pilot falls in mid-March 2027 and the week-28 launch in early June 2027. SSC 2027 is over and HSC 2027 is starting. The design's example "SSC Science 2027" cannot be a pilot cohort; use SSC 2028 or HSC 2028. Confirm the 2028 exam month. |
| 2026-27 admission tests run from about December 2026 to early 2027; reports disagree on dates ([students.bd](https://students.bd/en/news/public-university-admission-test-schedule-2026-2027), [Dhaka Tribune](https://www.dhakatribune.com/bangladesh/campus1/424358/jnu-announces-admission-test-schedule-for-2026-27)) | This season is missed. The next one follows HSC 2027 results. |
| One common SSC question paper across general boards, HSC later ([Dhaka Tribune](https://www.dhakatribune.com/bangladesh/education/413027/ssc-hsc-exams-to-follow-unified-question-papers%C2%A0)) | Board-wise past papers stay useful history. A national mock becomes closer to the real exam. |
| Written creative questions (CQ) carry most marks, commonly reported as 70 CQ / 30 MCQ without practical ([Shikkhaweb](https://www.shikkhaweb.com/en/ssc/mark-distribution), unofficial; sources disagree by subject) | **Largest gap.** At P0 CQ is self-marked and AI grading is P1. The app practises the smaller part of the exam. |
| SSC 2026: 1,829,485 candidates, 62.25% passed, 690,608 failed ([Prothom Alo](https://en.prothomalo.com/youth/education/7t771sup99), [Dhaka Tribune](https://www.dhakatribune.com/bangladesh/417108/ssc-results-6-90-608-students-fail)) | A large group needs to pass, not to rank. The design is built around Science and ranking. |
| HSC 2026: 1,270,583 candidates, 52.12% passed ([Prothom Alo](https://en.prothomalo.com/youth/education/s20r4aqd2s)) | Same. |
| 72.4% of households own a smartphone, 68.8% rural; 48.9% of people aged 5+ use the internet ([Financial Express](https://thefinancialexpress.com.bd/home/mobile-internet-access-expand-despite-ownership-gender-gaps-bbs-survey)) | Low-end Android, lite mode and offline are right. Offline packs being P1 is a risk. A household phone is often shared, and shared profiles (AUTH-08) are P1. |
| Personal Data Protection Act 2026: under-18 needs guardian consent; commentary also reports a ban on profiling and behavioural tracking of minors ([Securiti](https://securiti.ai/bangladesh-personal-data-protection-act-overview/), secondary) | **Legal check before build (D4).** Could affect adaptive practice, mistake diagnosis, study-time push and leaderboards. |
| NCTB halted printing of note and guide books until 31 Dec 2026 ([TBS](https://www.tbsnews.net/bangladesh/education/nctb-suspends-printing-binding-all-notes-guidebooks-until-31-dec-1610806)) | A printing order, not about apps. Textbook licence (D1) stays open. |

## 3. Competitors

Claims come from the vendors' own pages or listings unless noted. "–" means not found in this research, not proven absent.

| App | Focus | AI tutor | Photo solve | CQ | Exams | Streak / leaderboard | Scale or price signal |
|---|---|---|---|---|---|---|---|
| [Chorcha](https://chorcha.net/) | SSC, HSC, admission, BCS, jobs | Yes, "from your book" | – | Bank and AI explanation | Mock and model tests | Both | Claims 1M+ downloads, 10 lakh+ questions. [2024 plans Tk 199–1,439](https://chorcha.net/blog/chorcha-subscription) |
| [Shikho](https://play.google.com/store/apps/details?id=tech.shikho.android) | School, classes | Yes, Bangla, NCTB | Reported in beta (2025) | – | Yes | Badges, points, leaderboard | Says $8M+ raised ([Daily Star](https://www.thedailystar.net/business/news/edtech-startups-look-beyond-user-growth-4311476)) |
| [10 Minute School](https://apps.apple.com/us/app/10-minute-school/id1577061772) | Class 1–12, admission, jobs, skills | TenTen AI | "SuperSolve", function unclear | – | Model tests, quizzes | Leaderboard | Tk 50 crore revenue, 50,000+ paying ([Daily Star](https://www.thedailystar.net/business/news/edtech-startups-look-beyond-user-growth-4311476)) |
| [Live MCQ](https://play.google.com/store/apps/details?id=com.livemcq.livemcq) | BCS and jobs | – | – | – | Live exams | – | Claims 2.4M+ users; $15.99 a year on the US App Store |
| Udvash-Unmesh | Coaching, admission | – | – | – | Live and recorded classes, exams | – | Offline coaching brand |
| [Oddhoyon](https://play.google.com/store/apps/details?id=com.oddhoyon.ai) | Class 6–8, SSC, HSC, admission | Yes | Yes | Practice | Timed, negative marking | – | Listing dated Oct 2026 |
| [Poripurok](https://play.google.com/store/apps/details?id=com.poripurok.app) | Class 9 to admission | Yes | Yes | – | Exam prep | – | 10 free solves, bKash premium |
| [Porikkha](https://porikkhaai.live/) | School to HSC | Voice tutor | Yes (maths) | "CQ solver" | MCQ | – | Says core is free |
| [MindSync](https://play.google.com/store/apps/details?id=com.MindSync.aab) | SSC, HSC, admission | Yes | – | – | Question bank | Spaced repetition | 10K+ downloads |
| ChatGPT, Gemini | General | Yes | Yes | General feedback | – | – | Free tiers; Bangla supported |

## 4. Feature by feature

| Planned feature | Status in market | Stands out? |
|---|---|---|
| Question bank, past papers, mocks | Common; Chorcha claims several times the planned 150,000 | No |
| Bangla / Banglish AI tutor | Several | No |
| Photo solve | Several | No |
| XP, streak, leaderboard | Chorcha, Shikho | No |
| Multi-track school to admission to job | Chorcha and 10 Minute School cover these stages | Weak (kept history may be new) |
| Citation to textbook page, "not sure" refusal | Not advertised by any found | **Possible**, needs D1 |
| Two-person verified answer keys, visible error fixes | Not advertised | **Possible**, if shown to students |
| Mistake Notebook driving next practice | Not advertised in what was read | Weak to medium |
| CQ marking by rubric from a handwritten photo | No app found claiming it | **Strongest**, currently P1 |
| 200,000-student live exam | Invisible until it fails | No |
| Teacher, coaching and parent tools | Not researched | Unknown, P1 |

## 5. Business risks

- **Free tier cost.** Design §8.6 prices a message at $0.0027 and a photo solve at $0.022. A free user using the full 10 messages and 2 photos costs about $0.071 a day, near Tk 260 a month. Chorcha's 2024 entry plan was Tk 199 (period not stated). Cut the free photo quota or serve cached and verified answers first.
- **Content.** Verification status of the bank is unknown; this decides both quality and the date.
- **Distribution.** The documents read for this report give no plan for how students find the app against funded brands.
- **Scope.** 87 P0 requirements aim at parity with established players on every front at once.

## 6. Recommendation

**Position:** "Write the answer by hand, get marks the way an examiner gives them, with the textbook reference." One cohort (SSC 2028), two or three subjects.

1. Move CQ photo grading (AI-07, AI-07a, AI-07b) to P0.
2. Keep: verified bank for those subjects, Mistake Notebook, citations, simple streak.
3. Defer: admission and job tracks, 200,000-student exams, national leaderboards, Classes 6–8.
4. Interview coaching teachers as possible buyers: CQ marking is their manual work.

**Test before building** (about 4 weeks, no app needed). Thresholds are proposals.

| Test | Pass |
|---|---|
| 200 real handwritten CQ answers, graded by AI and two teachers | AI agrees with teachers about as well as they agree with each other |
| 30 students and 10 teachers interviewed; AI grading, checked by hand, offered over chat | Most return for a second week; some pay |
| Same 50 questions put to Chorcha, Shikho, ChatGPT and our prompt | Ours is clearly better on correctness and citation |
| Legal opinion on D1 (textbooks) and D4 (minors) | Written answer |

Collecting answers from minors needs guardian consent. If AI grading fails the first test, the fallback (verified, cited answers) is much weaker; reconsider before funding a 10-person build.

## 7. Not verified

- Current competitor prices; install counts other than vendor claims.
- Hands-on quality of any competitor's AI. Several store pages could not be opened directly; their rows rest on search summaries.
- Official 2027–2028 mark distribution, curriculum rollout order and exam months.
- Gazetted text of the data protection law.
- Admission and BCS applicant numbers; current guidebook and tutoring spend.
- Willingness to pay.
